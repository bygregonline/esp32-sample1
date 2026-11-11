//! BLE GATT snapshot service. Clients read one characteristic to select encoding.
use std::sync::atomic::{AtomicBool, AtomicU16, Ordering};

use enumset::enum_set;
use esp_idf_svc::{
    ble::{
        ensure_addr,
        gap::{BleAdvFields, BleAdvParams, GapEvent},
        gatt::{
            server::{
                BleGattCharacteristic, BleGattRegister, BleGattService, BleGattServices, GattsEvent,
            },
            BleGattCharFlag,
        },
        BleDriver, BleUuid, HostEvent,
    },
    hal::{delay::FreeRtos, modem::BluetoothModemPeripheral},
};

use crate::monitor_state::MonitorState;

const SERVICE_UUID: u16 = 0xFFA0;
const FORMAT_UUIDS: [u16; 4] = [0xFFA1, 0xFFA2, 0xFFA3, 0xFFA4];
static HANDLES: [AtomicU16; 4] = [
    AtomicU16::new(0),
    AtomicU16::new(0),
    AtomicU16::new(0),
    AtomicU16::new(0),
];
static NEEDS_ADV: AtomicBool = AtomicBool::new(false);

pub fn start<M: BluetoothModemPeripheral + Send + 'static>(
    modem: M,
    state: MonitorState,
) -> anyhow::Result<()> {
    std::thread::Builder::new()
        .name("ble-gatt".into())
        .stack_size(8192)
        .spawn(move || {
            let chars = FORMAT_UUIDS
                .iter()
                .map(|u| {
                    BleGattCharacteristic::new(
                        BleUuid::uuid16(*u),
                        enum_set!(BleGattCharFlag::Read),
                    )
                })
                .collect();
            let services = BleGattServices::new(vec![BleGattService::new(
                true,
                BleUuid::uuid16(SERVICE_UUID),
                chars,
            )]);
            let driver = match BleDriver::new_with_services(modem, services) {
                Ok(d) => d,
                Err(e) => {
                    log::error!("BLE init error: {e}");
                    return;
                }
            };
            driver.gatts_subscribe(move |event| {
                match event {
                    GattsEvent::Register(BleGattRegister::Characteristic {
                        uuid,
                        val_handle,
                        ..
                    }) => {
                        for (i, id) in FORMAT_UUIDS.iter().enumerate() {
                            if uuid == BleUuid::uuid16(*id) {
                                HANDLES[i].store(val_handle, Ordering::Relaxed);
                            }
                        }
                    }
                    GattsEvent::Read {
                        attr_handle,
                        mut reply,
                        ..
                    } => {
                        let Some(index) = HANDLES
                            .iter()
                            .position(|h| h.load(Ordering::Relaxed) == attr_handle)
                        else {
                            return 0;
                        };
                        let value = representation(&state, index);
                        if reply.append(value.as_bytes()).is_err() {
                            return 1;
                        }
                    }
                    _ => {}
                }
                0
            });
            driver.host_subscribe(|event| {
                if let HostEvent::Sync = event {
                    NEEDS_ADV.store(true, Ordering::Relaxed);
                }
            });
            driver.gap_subscribe(|event| {
                if let GapEvent::Disconnect { .. } = event {
                    NEEDS_ADV.store(true, Ordering::Relaxed);
                }
                0
            });
            if let Err(e) = driver.start() {
                log::error!("BLE host start error: {e}");
                return;
            }
            loop {
                FreeRtos::delay_ms(500);
                if NEEDS_ADV.swap(false, Ordering::Relaxed) {
                    if let Err(e) = advertise(&driver) {
                        log::warn!("BLE advertising error: {e}");
                    }
                }
            }
        })?;
    Ok(())
}

fn representation(state: &MonitorState, format: usize) -> String {
    let d = state.snapshot();
    let time = crate::display::clock_text();
    let elapsed = (esp_idf_svc::systime::EspSystemTime {}.now().as_millis() as u64)
        .saturating_sub(d.last_sensor_read_ms)
        / 1000;
    let rem = d.sensor_interval_secs.saturating_sub(elapsed as u32);
    let lat = if d.gps_fix {
        format!("{:.6}", d.latitude)
    } else {
        "null".into()
    };
    let lon = if d.gps_fix {
        format!("{:.6}", d.longitude)
    } else {
        "null".into()
    };
    let temp = if d.dht_valid {
        format!("{:.1}", d.temperature_c)
    } else {
        "null".into()
    };
    let hum = if d.dht_valid {
        format!("{:.1}", d.humidity_percent)
    } else {
        "null".into()
    };
    let pressure = if d.bmp280_valid {
        format!("{:.1}", d.pressure_hpa)
    } else {
        "null".into()
    };
    let forecast = if d.weather.valid {
        d.weather.summary.as_str()
    } else {
        "unavailable"
    };
    let forecast_json = if d.weather.valid {
        format!("\"{}\"", json_escape(forecast))
    } else {
        "null".into()
    };
    let forecast_yaml = if d.weather.valid {
        format!("\"{}\"", forecast.replace('"', "\\\""))
    } else {
        "null".into()
    };
    let forecast_xml = if d.weather.valid {
        xml_escape(forecast)
    } else {
        String::new()
    };
    let ssid_json = json_escape(&d.wifi_ssid);
    let ssid_xml = xml_escape(&d.wifi_ssid);
    let ip_json = json_escape(&d.ip_address);
    let ip_xml = xml_escape(&d.ip_address);
    let event_json = json_escape(d.events.last().map(String::as_str).unwrap_or("none"));
    let event_xml = xml_escape(d.events.last().map(String::as_str).unwrap_or("none"));
    let wtemp = if d.weather.valid {
        format!("{:.1}", d.weather.current_temperature_c)
    } else {
        "null".into()
    };
    let whum = if d.weather.valid {
        format!("{:.1}", d.weather.current_humidity_percent)
    } else {
        "null".into()
    };
    let wmin = if d.weather.valid {
        format!("{:.1}", d.weather.minimum_temperature_c)
    } else {
        "null".into()
    };
    let wmax = if d.weather.valid {
        format!("{:.1}", d.weather.maximum_temperature_c)
    } else {
        "null".into()
    };
    let rain = if d.weather.valid {
        d.weather.precipitation_probability.to_string()
    } else {
        "null".into()
    };
    let moon = if d.moon_phase_valid {
        format!("{:.3}", d.moon_phase)
    } else {
        "null".into()
    };
    let illum = if d.moon_phase_valid {
        d.moon_illumination_percent.to_string()
    } else {
        "null".into()
    };
    let event = d.events.last().map(String::as_str).unwrap_or("none");
    match format {
        0 => format!(r#"{{"time":"{time}","ip":"{ip_json}","wifi":{},"ssid":"{ssid_json}","battery_v":{:.3},"temp_c":{temp},"hum_pct":{hum},"pressure_hpa":{pressure},"lat":{lat},"lon":{lon},"forecast":{forecast_json},"wx_c":{wtemp},"wx_hum_pct":{whum},"wx_min_c":{wmin},"wx_max_c":{wmax},"rain_pct":{rain},"moon":{moon},"moon_illum_pct":{illum},"interval_s":{},"remaining_s":{rem},"event":"{event_json}"}}"#, d.wifi_connected, d.battery_voltage, d.sensor_interval_secs),
        1 => format!("time={time}\nip={}\nwifi={}\nssid={}\nbattery_v={:.3}\ntemp_c={temp}\nhum_pct={hum}\npressure_hpa={pressure}\nlat={lat}\nlon={lon}\nforecast={forecast}\nwx_c={wtemp}\nwx_hum_pct={whum}\nwx_min_c={wmin}\nwx_max_c={wmax}\nrain_pct={rain}\nmoon={moon}\nmoon_illum_pct={illum}\ninterval_s={}\nremaining_s={rem}\nevent={event}", d.ip_address, d.wifi_connected, d.wifi_ssid, d.battery_voltage, d.sensor_interval_secs),
        2 => format!("time: \"{time}\"\nip: \"{}\"\nwifi: {}\nssid: \"{}\"\nbattery_v: {:.3}\ntemp_c: {temp}\nhum_pct: {hum}\npressure_hpa: {pressure}\nlat: {lat}\nlon: {lon}\nforecast: {forecast_yaml}\nwx_c: {wtemp}\nwx_hum_pct: {whum}\nwx_min_c: {wmin}\nwx_max_c: {wmax}\nrain_pct: {rain}\nmoon: {moon}\nmoon_illum_pct: {illum}\ninterval_s: {}\nremaining_s: {rem}\nevent: \"{event}\"", d.ip_address, d.wifi_connected, d.wifi_ssid, d.battery_voltage, d.sensor_interval_secs),
        _ => format!("<monitor time=\"{time}\" ip=\"{ip_xml}\" wifi=\"{}\" ssid=\"{ssid_xml}\" battery_v=\"{:.3}\" temp_c=\"{temp}\" hum_pct=\"{hum}\" pressure_hpa=\"{pressure}\" lat=\"{lat}\" lon=\"{lon}\" forecast=\"{forecast_xml}\" wx_c=\"{wtemp}\" wx_hum_pct=\"{whum}\" wx_min_c=\"{wmin}\" wx_max_c=\"{wmax}\" rain_pct=\"{rain}\" moon=\"{moon}\" moon_illum_pct=\"{illum}\" interval_s=\"{}\" remaining_s=\"{rem}\" event=\"{event_xml}\"/>", d.wifi_connected, d.battery_voltage, d.sensor_interval_secs),
    }
}

fn json_escape(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}

fn xml_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn advertise<S>(driver: &BleDriver<'_, S>) -> Result<(), esp_idf_svc::ble::BleError> {
    const NAME: &str = "ESP32-Monitor";
    ensure_addr(false)?;
    driver.set_device_name(NAME)?;
    driver.adv_set_fields(&BleAdvFields {
        flags: 0x06,
        name: Some(NAME),
        ..Default::default()
    })?;
    driver.adv_start(
        0,
        &BleAdvParams {
            conn_mode: 2,
            disc_mode: 2,
            itvl_min: 0x30,
            itvl_max: 0x60,
            ..Default::default()
        },
    )
}
