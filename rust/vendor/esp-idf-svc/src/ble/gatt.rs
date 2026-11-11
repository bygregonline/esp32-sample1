//! NimBLE GATT: shared types and helpers.

use core::ffi::c_int;

#[cfg(esp_idf_bt_nimble_gatt_server)]
use enumset::{EnumSet, EnumSetType};

use crate::sys::*;

use super::{BleError, ConnHandle};

#[cfg(esp_idf_bt_nimble_gatt_client)]
pub mod client;
#[cfg(esp_idf_bt_nimble_gatt_server)]
pub mod server;

/// A GATT attribute handle (e.g. a characteristic's value handle).
pub type AttrHandle = u16;

/// Set the preferred ATT MTU. Safe to call before or after the host starts.
pub fn set_preferred_mtu(mtu: u16) -> Result<(), BleError> {
    BleError::from_raw(unsafe { ble_att_set_preferred_mtu(mtu) })
}

/// The negotiated ATT MTU for a connection
pub fn att_mtu(conn_handle: ConnHandle) -> Result<u16, BleError> {
    match unsafe { ble_att_mtu(conn_handle) } {
        0 => Err(BleError::new(BLE_HS_ENOTCONN as c_int)),
        mtu => Ok(mtu),
    }
}

/// A GATT characteristic operation / permission flag (`BLE_GATT_CHR_F_*`).
///
/// The operation flags become the property bits of the characteristic declaration (and gate what
/// the ATT server lets a peer do); the `*Enc` / `*Authen` / `*Author` flags additionally demand a
/// security level before the access is dispatched to the
/// [`gatts_subscribe`](crate::ble::BleDriver::gatts_subscribe) hook.
#[cfg(esp_idf_bt_nimble_gatt_server)]
#[derive(Debug, EnumSetType)]
pub enum BleGattCharFlag {
    /// The value may be broadcast (sets the Broadcast property bit).
    Broadcast,
    /// The peer may read the value.
    Read,
    /// The peer may write the value **without** a response (ATT Write Command). Independent of
    /// [`Write`](Self::Write) — a peer cannot use write-without-response unless this flag is set —
    /// but both kinds of write arrive as the same
    /// [`GattsEvent::Write`](server::GattsEvent::Write), as NimBLE does not report which ATT
    /// opcode carried them.
    WriteNoRsp,
    /// The peer may write the value **with** a response (ATT Write Request).
    Write,
    /// The value may be notified (unacknowledged). NimBLE adds the CCCD for you.
    Notify,
    /// The value may be indicated (acknowledged). NimBLE adds the CCCD for you.
    Indicate,
    /// The peer may write the value with a signature (ATT Signed Write Command).
    AuthSignWrite,
    /// Sets the "Reliable Write" extended property (prepare/execute writes). The queued writes are
    /// coalesced by NimBLE and delivered as a single [`Write`](server::GattsEvent::Write).
    ReliableWrite,
    /// Sets the "Writable Auxiliaries" extended property (the Characteristic User Description
    /// descriptor is writable).
    AuxWrite,
    /// Reads require an encrypted link.
    ReadEnc,
    /// Reads require an encrypted link from an authenticated (MITM-protected) pairing.
    ReadAuthen,
    /// Reads require authorization.
    ///
    /// **Not usable yet:** NimBLE asks the application to authorize the access through the
    /// `BLE_GAP_EVENT_AUTHORIZE` GAP event, which this crate does not surface (it arrives as
    /// [`GapEvent::Other`](crate::ble::gap::GapEvent::Other), whose response cannot be set), and
    /// NimBLE rejects an unanswered request — so setting this flag currently fails every read with
    /// "insufficient authorization".
    ReadAuthor,
    /// Writes require an encrypted link.
    WriteEnc,
    /// Writes require an encrypted link from an authenticated (MITM-protected) pairing.
    WriteAuthen,
    /// Writes require authorization. Carries the same caveat as [`ReadAuthor`](Self::ReadAuthor).
    WriteAuthor,
    /// Subscribing (writing the CCCD) requires an encrypted link.
    #[cfg(esp_idf_version_at_least_5_5_0)]
    NotifyIndicateEnc,
    /// Subscribing (writing the CCCD) requires an encrypted link from an authenticated
    /// (MITM-protected) pairing.
    #[cfg(esp_idf_version_at_least_5_5_0)]
    NotifyIndicateAuthen,
    /// Subscribing (writing the CCCD) requires authorization. Carries the same caveat as
    /// [`ReadAuthor`](Self::ReadAuthor).
    #[cfg(esp_idf_version_at_least_5_5_0)]
    NotifyIndicateAuthor,
}

#[cfg(esp_idf_bt_nimble_gatt_server)]
impl BleGattCharFlag {
    /// The raw NimBLE flag bit (`BLE_GATT_CHR_F_*`). `const`, so it can be used to build a static
    /// service table (see the [`gatt_services!`](crate::gatt_services) macro).
    pub const fn repr(self) -> ble_gatt_chr_flags {
        match self {
            Self::Broadcast => BLE_GATT_CHR_F_BROADCAST as ble_gatt_chr_flags,
            Self::Read => BLE_GATT_CHR_F_READ as ble_gatt_chr_flags,
            Self::WriteNoRsp => BLE_GATT_CHR_F_WRITE_NO_RSP as ble_gatt_chr_flags,
            Self::Write => BLE_GATT_CHR_F_WRITE as ble_gatt_chr_flags,
            Self::Notify => BLE_GATT_CHR_F_NOTIFY as ble_gatt_chr_flags,
            Self::Indicate => BLE_GATT_CHR_F_INDICATE as ble_gatt_chr_flags,
            Self::AuthSignWrite => BLE_GATT_CHR_F_AUTH_SIGN_WRITE as ble_gatt_chr_flags,
            Self::ReliableWrite => BLE_GATT_CHR_F_RELIABLE_WRITE as ble_gatt_chr_flags,
            Self::AuxWrite => BLE_GATT_CHR_F_AUX_WRITE as ble_gatt_chr_flags,
            Self::ReadEnc => BLE_GATT_CHR_F_READ_ENC as ble_gatt_chr_flags,
            Self::ReadAuthen => BLE_GATT_CHR_F_READ_AUTHEN as ble_gatt_chr_flags,
            Self::ReadAuthor => BLE_GATT_CHR_F_READ_AUTHOR as ble_gatt_chr_flags,
            Self::WriteEnc => BLE_GATT_CHR_F_WRITE_ENC as ble_gatt_chr_flags,
            Self::WriteAuthen => BLE_GATT_CHR_F_WRITE_AUTHEN as ble_gatt_chr_flags,
            Self::WriteAuthor => BLE_GATT_CHR_F_WRITE_AUTHOR as ble_gatt_chr_flags,
            // The CCCD-write permission flags only exist from ESP-IDF 5.5 on.
            #[cfg(esp_idf_version_at_least_5_5_0)]
            Self::NotifyIndicateEnc => BLE_GATT_CHR_F_NOTIFY_INDICATE_ENC as ble_gatt_chr_flags,
            #[cfg(esp_idf_version_at_least_5_5_0)]
            Self::NotifyIndicateAuthen => BLE_GATT_CHR_F_NOTIFY_INDICATE_AUTHEN as ble_gatt_chr_flags,
            #[cfg(esp_idf_version_at_least_5_5_0)]
            Self::NotifyIndicateAuthor => BLE_GATT_CHR_F_NOTIFY_INDICATE_AUTHOR as ble_gatt_chr_flags,
        }
    }
}

#[cfg(esp_idf_bt_nimble_gatt_server)]
impl From<BleGattCharFlag> for ble_gatt_chr_flags {
    fn from(flag: BleGattCharFlag) -> Self {
        flag.repr()
    }
}

#[cfg(esp_idf_bt_nimble_gatt_server)]
pub(crate) fn flags_to_repr(flags: EnumSet<BleGattCharFlag>) -> ble_gatt_chr_flags {
    flags
        .iter()
        .fold(0, |acc, flag| acc | ble_gatt_chr_flags::from(flag))
}
