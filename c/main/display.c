#include "display.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "config.h"
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_check.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* ── Constantes de pantalla ─────────────────────────────────────────────── */
#define OLED_CONTROL_COMMAND 0x00
#define OLED_CONTROL_DATA 0x40
#define OLED_COLUMNS 128
#define OLED_PAGES 8

/* Buffer DMA para transferencias de línea del LCD. */
static DMA_ATTR uint8_t lcd_line_buffer[LCD_WIDTH * 8 * 2];

/* ── Fuente 5×7 (5 columnas, bit 0 = fila superior) ─────────────────────── */
static const char font_chars[] = " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:.-%/";
static const uint8_t font[][5] = {
    {0x00, 0x00, 0x00, 0x00, 0x00}, /* ' '  */
    {0x3e, 0x51, 0x49, 0x45, 0x3e}, /* '0'  */
    {0x00, 0x42, 0x7f, 0x40, 0x00}, /* '1'  */
    {0x42, 0x61, 0x51, 0x49, 0x46}, /* '2'  */
    {0x21, 0x41, 0x45, 0x4b, 0x31}, /* '3'  */
    {0x18, 0x14, 0x12, 0x7f, 0x10}, /* '4'  */
    {0x27, 0x45, 0x45, 0x45, 0x39}, /* '5'  */
    {0x3c, 0x4a, 0x49, 0x49, 0x30}, /* '6'  */
    {0x01, 0x71, 0x09, 0x05, 0x03}, /* '7'  */
    {0x36, 0x49, 0x49, 0x49, 0x36}, /* '8'  */
    {0x06, 0x49, 0x49, 0x29, 0x1e}, /* '9'  */
    {0x7e, 0x11, 0x11, 0x11, 0x7e}, /* 'A'  */
    {0x7f, 0x49, 0x49, 0x49, 0x36}, /* 'B'  */
    {0x3e, 0x41, 0x41, 0x41, 0x22}, /* 'C'  */
    {0x7f, 0x41, 0x41, 0x22, 0x1c}, /* 'D'  */
    {0x7f, 0x49, 0x49, 0x49, 0x41}, /* 'E'  */
    {0x7f, 0x09, 0x09, 0x09, 0x01}, /* 'F'  */
    {0x3e, 0x41, 0x49, 0x49, 0x7a}, /* 'G'  */
    {0x7f, 0x08, 0x08, 0x08, 0x7f}, /* 'H'  */
    {0x00, 0x41, 0x7f, 0x41, 0x00}, /* 'I'  */
    {0x20, 0x40, 0x41, 0x3f, 0x01}, /* 'J'  */
    {0x7f, 0x08, 0x14, 0x22, 0x41}, /* 'K'  */
    {0x7f, 0x40, 0x40, 0x40, 0x40}, /* 'L'  */
    {0x7f, 0x02, 0x0c, 0x02, 0x7f}, /* 'M'  */
    {0x7f, 0x04, 0x08, 0x10, 0x7f}, /* 'N'  */
    {0x3e, 0x41, 0x41, 0x41, 0x3e}, /* 'O'  */
    {0x7f, 0x09, 0x09, 0x09, 0x06}, /* 'P'  */
    {0x3e, 0x41, 0x51, 0x21, 0x5e}, /* 'Q'  */
    {0x7f, 0x09, 0x19, 0x29, 0x46}, /* 'R'  */
    {0x46, 0x49, 0x49, 0x49, 0x31}, /* 'S'  */
    {0x01, 0x01, 0x7f, 0x01, 0x01}, /* 'T'  */
    {0x3f, 0x40, 0x40, 0x40, 0x3f}, /* 'U'  */
    {0x1f, 0x20, 0x40, 0x20, 0x1f}, /* 'V'  */
    {0x3f, 0x40, 0x38, 0x40, 0x3f}, /* 'W'  */
    {0x63, 0x14, 0x08, 0x14, 0x63}, /* 'X'  */
    {0x07, 0x08, 0x70, 0x08, 0x07}, /* 'Y'  */
    {0x61, 0x51, 0x49, 0x45, 0x43}, /* 'Z'  */
    {0x00, 0x36, 0x36, 0x00, 0x00}, /* ':'  */
    {0x00, 0x60, 0x60, 0x00, 0x00}, /* '.'  */
    {0x08, 0x08, 0x08, 0x08, 0x08}, /* '-'  */
    {0x08, 0x14, 0x2a, 0x14, 0x22}, /* '%'  */
    {0x20, 0x10, 0x08, 0x04, 0x02}, /* '/'  */
};

/* ── Utilidades de color RGB565 ─────────────────────────────────────────── */
static uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
    return (uint16_t)(((r & 0xf8u) << 8) | ((g & 0xfcu) << 3) | (b >> 3));
}

/* ── Transferencias SPI / LCD ────────────────────────────────────────────── */
static esp_err_t lcd_transfer(display_t *d, const void *data, size_t size, int dc) {
    gpio_set_level(LCD_DC_GPIO, dc);
    spi_transaction_t t = {.length = size * 8, .tx_buffer = data};
    return spi_device_transmit(d->lcd, &t);
}

static esp_err_t lcd_command(display_t *d, uint8_t cmd, const uint8_t *data, size_t len) {
    esp_err_t r = lcd_transfer(d, &cmd, 1, 0);
    if (r == ESP_OK && len) {
        r = lcd_transfer(d, data, len, 1);
    }
    return r;
}

static void lcd_set_window(display_t *d, int x, int y, int w, int h) {
    const int x0 = x + LCD_X_OFFSET, x1 = x0 + w - 1;
    const int y1         = y + h - 1;
    const uint8_t cols[] = {x0 >> 8, x0 & 0xff, x1 >> 8, x1 & 0xff};
    const uint8_t rows[] = {y >> 8, y & 0xff, y1 >> 8, y1 & 0xff};
    (void)lcd_command(d, 0x2a, cols, 4);
    (void)lcd_command(d, 0x2b, rows, 4);
    const uint8_t mem_wr = 0x2c;
    (void)lcd_transfer(d, &mem_wr, 1, 0);
}

/* ── Fuente ─────────────────────────────────────────────────────────────── */
static const uint8_t *glyph_for(char c) {
    c             = (char)toupper((unsigned char)c);
    const char *p = strchr(font_chars, c);
    return p ? font[p - font_chars] : font[0];
}

/* ── Primitivas de dibujo en LCD ─────────────────────────────────────────── */
static void lcd_draw_char(display_t *d, char c, int x, int y, uint16_t fg, uint16_t bg) {
    uint8_t pixels[6 * 8 * 2];
    const uint8_t *g = glyph_for(c);
    size_t off       = 0;
    for (int row = 0; row < 8; ++row) {
        for (int col = 0; col < 6; ++col) {
            const bool on     = col < 5 && row < 7 && ((g[col] >> row) & 1);
            const uint16_t px = on ? fg : bg;
            pixels[off++]     = px >> 8;
            pixels[off++]     = px & 0xff;
        }
    }
    lcd_set_window(d, x, y, 6, 8);
    (void)lcd_transfer(d, pixels, sizeof(pixels), 1);
}

static void lcd_draw_text(display_t *d, const char *text, int x, int y, uint16_t color) {
    if (x < 0 || x >= LCD_WIDTH || y < 0 || y + 8 > LCD_HEIGHT)
        return;
    const int cols  = (LCD_WIDTH - x) / 6;
    const int width = cols * 6;
    const int tlen  = (int)strlen(text);

    for (int row = 0; row < 8; ++row) {
        for (int ch = 0; ch < cols; ++ch) {
            const char val   = ch < tlen ? text[ch] : ' ';
            const uint8_t *g = glyph_for(val);
            for (int col = 0; col < 6; ++col) {
                const bool on            = col < 5 && row < 7 && ((g[col] >> row) & 1);
                const uint16_t px        = on ? color : 0x0000;
                const int off            = (row * width + ch * 6 + col) * 2;
                lcd_line_buffer[off]     = px >> 8;
                lcd_line_buffer[off + 1] = px & 0xff;
            }
        }
    }
    lcd_set_window(d, x, y, width, 8);
    (void)lcd_transfer(d, lcd_line_buffer, (size_t)(width * 8 * 2), 1);
}

/* Dibuja una línea horizontal delgada (separador). */
static void lcd_draw_hline(display_t *d, int y, uint16_t color) {
    for (int i = 0; i < LCD_WIDTH * 2; i += 2) {
        lcd_line_buffer[i]     = color >> 8;
        lcd_line_buffer[i + 1] = color & 0xff;
    }
    lcd_set_window(d, 0, y, LCD_WIDTH, 1);
    (void)lcd_transfer(d, lcd_line_buffer, (size_t)(LCD_WIDTH * 2), 1);
}

/* Anillo de progreso para el countdown del ciclo de sensores. */
static void lcd_draw_refresh_ring(display_t *d, int cx, int cy, int radius, int remaining,
                                  uint32_t interval) {
    const int diameter = radius * 2 + 1;
    const int inner_r  = radius - 4;
    const float progress =
        remaining < 0 || interval == 0 ? 0.0f : fminf(1.0f, (float)remaining / (float)interval);
    const float angle_end = progress * 6.28318530718f;

    const uint16_t track_color = rgb565(42, 58, 67);
    const uint16_t arc_color   = progress > 0.5f   ? rgb565(0, 210, 120)
                                 : progress > 0.2f ? rgb565(255, 185, 0)
                                                   : rgb565(240, 60, 60);

    uint8_t row[(2 * 44 + 1) * 2];
    for (int dy = -radius; dy <= radius; ++dy) {
        for (int dx = -radius; dx <= radius; ++dx) {
            const int dsq = dx * dx + dy * dy;
            uint16_t c    = 0x0000;
            if (dsq <= radius * radius && dsq >= inner_r * inner_r) {
                float ang = atan2f((float)dx, (float)-dy);
                if (ang < 0)
                    ang += 6.28318530718f;
                c = ang <= angle_end ? arc_color : track_color;
            }
            const int px    = dx + radius;
            row[px * 2]     = c >> 8;
            row[px * 2 + 1] = c & 0xff;
        }
        lcd_set_window(d, cx - radius, cy + dy, diameter, 1);
        (void)lcd_transfer(d, row, (size_t)(diameter * 2), 1);
    }
}

/* Miniature moon disk with a phase-shaped terminator for the color LCD. */
static void lcd_draw_moon_icon(display_t *d, int cx, int cy, float phase, bool valid) {
    const int radius = 10;
    const int diameter = radius * 2 + 1;
    const float angle = (valid ? phase : 0.0f) * 6.28318530718f;
    const float sun_x = sinf(angle);
    const float sun_z = -cosf(angle);
    uint8_t row[21 * 2];

    for (int dy = -radius; dy <= radius; ++dy) {
        for (int dx = -radius; dx <= radius; ++dx) {
            const float nx = (float)dx / radius;
            const float ny = (float)dy / radius;
            const float r2 = nx * nx + ny * ny;
            uint16_t color = 0x0000;
            if (r2 <= 1.0f) {
                const float nz = sqrtf(1.0f - r2);
                const float light = nx * sun_x + nz * sun_z;
                const uint8_t shade = light > 0.0f ? (uint8_t)(175 + nz * 65) : 19;
                color = rgb565(shade, shade, (uint8_t)(shade + (light > 0.0f ? 5 : 4)));
                /* A few small maria/crater marks keep the disk recognizable. */
                const float c1x = nx - 0.28f, c1y = ny + 0.25f;
                const float c2x = nx + 0.35f, c2y = ny - 0.20f;
                if (light > 0.0f && (c1x * c1x + c1y * c1y < 0.025f ||
                                     c2x * c2x + c2y * c2y < 0.018f)) {
                    const uint8_t crater = shade > 35 ? (uint8_t)(shade - 35) : shade;
                    color = rgb565(crater, crater, crater);
                }
            }
            const int pixel = dx + radius;
            row[pixel * 2] = (uint8_t)(color >> 8);
            row[pixel * 2 + 1] = (uint8_t)color;
        }
        lcd_set_window(d, cx - radius, cy + dy, diameter, 1);
        (void)lcd_transfer(d, row, sizeof(row), 1);
    }
}

/* ── OLED (I2C directo, sin librería) ────────────────────────────────────── */
static esp_err_t oled_write(const uint8_t *data, size_t len) {
    return i2c_master_write_to_device(OLED_I2C_PORT, OLED_I2C_ADDRESS, data, len,
                                      pdMS_TO_TICKS(100));
}

static esp_err_t oled_command(display_t *d, uint8_t cmd) {
    (void)d;
    const uint8_t pkt[] = {OLED_CONTROL_COMMAND, cmd};
    return oled_write(pkt, 2);
}

static void oled_text(display_t *d, const char *text, int x, int y) {
    if (y < 0 || y >= 64)
        return;
    const int page = y / 8;
    while (*text && x + 6 <= OLED_COLUMNS) {
        const uint8_t *g = glyph_for(*text++);
        for (int col = 0; col < 5; ++col) {
            const int tx = x + col;
            if (tx >= 0 && tx < OLED_COLUMNS) {
                d->oled_buffer[page * OLED_COLUMNS + tx] = g[col];
            }
        }
        x += 6;
    }
}

static void oled_flush(display_t *d) {
    uint8_t pkt[OLED_COLUMNS + 1];
    for (int page = 0; page < OLED_PAGES; ++page) {
        const uint8_t addr[] = {OLED_CONTROL_COMMAND, (uint8_t)(0xb0 + page), 0x00, 0x10};
        (void)oled_write(addr, 4);
        pkt[0] = OLED_CONTROL_DATA;
        memcpy(pkt + 1, &d->oled_buffer[page * OLED_COLUMNS], OLED_COLUMNS);
        (void)oled_write(pkt, OLED_COLUMNS + 1);
    }
}

/* ── Inicialización ─────────────────────────────────────────────────────── */
esp_err_t display_init(display_t *display) {
    memset(display, 0, sizeof(*display));

    const gpio_config_t ctrl = {
        .pin_bit_mask = (1ULL << LCD_DC_GPIO) | (1ULL << LCD_RST_GPIO),
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&ctrl), "display", "LCD GPIO setup failed");

    const spi_bus_config_t bus = {
        .mosi_io_num     = LCD_MOSI_GPIO,
        .miso_io_num     = -1,
        .sclk_io_num     = LCD_SCK_GPIO,
        .quadwp_io_num   = -1,
        .quadhd_io_num   = -1,
        .max_transfer_sz = LCD_WIDTH * 8 * 2,
    };
    ESP_RETURN_ON_ERROR(spi_bus_initialize(LCD_SPI_HOST, &bus, SPI_DMA_CH_AUTO), "display",
                        "LCD SPI bus setup failed");

    const spi_device_interface_config_t dev = {
        .clock_speed_hz = 20 * 1000 * 1000,
        .mode           = 0,
        .spics_io_num   = LCD_CS_GPIO,
        .queue_size     = 1,
    };
    ESP_RETURN_ON_ERROR(spi_bus_add_device(LCD_SPI_HOST, &dev, &display->lcd), "display",
                        "LCD SPI device setup failed");

    /* Secuencia de reset y encendido del ST7789V2 */
    gpio_set_level(LCD_RST_GPIO, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(LCD_RST_GPIO, 1);
    vTaskDelay(pdMS_TO_TICKS(120));
    (void)lcd_command(display, 0x01, NULL, 0); /* SWRESET */
    vTaskDelay(pdMS_TO_TICKS(150));
    (void)lcd_command(display, 0x11, NULL, 0); /* SLPOUT */
    vTaskDelay(pdMS_TO_TICKS(120));

    const uint8_t pixel_fmt = 0x55;
#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
    const uint8_t mem_acc = 0x48;
    (void)lcd_command(display, 0x3a, &pixel_fmt, 1);
    (void)lcd_command(display, 0x36, &mem_acc, 1);
    (void)lcd_command(display, 0x21, NULL, 0);
    (void)lcd_command(display, 0x29, NULL, 0);
    vTaskDelay(pdMS_TO_TICKS(100));
#else
    const uint8_t mem_acc     = 0x00;
    const uint8_t porch[]     = {0x0c, 0x0c, 0x00, 0x33, 0x33};
    const uint8_t gate_ctrl   = 0x35;
    const uint8_t vcom        = 0x19;
    const uint8_t lcm         = 0x2c;
    const uint8_t vdv_en[]    = {0x01, 0xff};
    const uint8_t vrh         = 0x12;
    const uint8_t vdv         = 0x20;
    const uint8_t frame_rate  = 0x0f;
    const uint8_t power[]     = {0xa4, 0xa1};
    const uint8_t pos_gamma[] = {0xd0, 0x04, 0x0d, 0x11, 0x13, 0x2b, 0x3f,
                                 0x54, 0x4c, 0x18, 0x0d, 0x0b, 0x1f, 0x23};
    const uint8_t neg_gamma[] = {0xd0, 0x04, 0x0c, 0x11, 0x13, 0x2c, 0x3f,
                                 0x44, 0x51, 0x2f, 0x1f, 0x1f, 0x20, 0x23};
    (void)lcd_command(display, 0x3a, &pixel_fmt, 1);
    (void)lcd_command(display, 0x36, &mem_acc, 1);
    (void)lcd_command(display, 0xb2, porch, 5);
    (void)lcd_command(display, 0xb7, &gate_ctrl, 1);
    (void)lcd_command(display, 0xbb, &vcom, 1);
    (void)lcd_command(display, 0xc0, &lcm, 1);
    (void)lcd_command(display, 0xc2, vdv_en, 2);
    (void)lcd_command(display, 0xc3, &vrh, 1);
    (void)lcd_command(display, 0xc4, &vdv, 1);
    (void)lcd_command(display, 0xc6, &frame_rate, 1);
    (void)lcd_command(display, 0xd0, power, 2);
    (void)lcd_command(display, 0xe0, pos_gamma, 14);
    (void)lcd_command(display, 0xe1, neg_gamma, 14);
    (void)lcd_command(display, 0x21, NULL, 0); /* INVON  */
    (void)lcd_command(display, 0x13, NULL, 0); /* NORON  */
    (void)lcd_command(display, 0x29, NULL, 0); /* DISPON */
    vTaskDelay(pdMS_TO_TICKS(100));
#endif

    /* I2C para el OLED SSD1306 */
    const i2c_config_t i2c = {
        .mode             = I2C_MODE_MASTER,
        .sda_io_num       = OLED_SDA_GPIO,
        .scl_io_num       = OLED_SCL_GPIO,
        .sda_pullup_en    = GPIO_PULLUP_ENABLE,
        .scl_pullup_en    = GPIO_PULLUP_ENABLE,
        .master.clk_speed = 400000,
    };
    ESP_RETURN_ON_ERROR(i2c_param_config(OLED_I2C_PORT, &i2c), "display", "OLED I2C config failed");
    ESP_RETURN_ON_ERROR(i2c_driver_install(OLED_I2C_PORT, I2C_MODE_MASTER, 0, 0, 0), "display",
                        "OLED I2C install failed");

    const uint8_t oled_init[] = {
        0xae, 0xd5, 0x80, 0xa8, 0x3f, 0xd3, 0x00, 0x40, 0x8d, 0x14, 0x20, 0x02, 0xa1,
        0xc8, 0xda, 0x12, 0x81, 0xcf, 0xd9, 0xf1, 0xdb, 0x40, 0xa4, 0xa6, 0xaf,
    };
    for (size_t i = 0; i < sizeof(oled_init); ++i) {
        ESP_RETURN_ON_ERROR(oled_command(display, oled_init[i]), "display",
                            "OLED init failed; check I2C wiring");
    }
    return ESP_OK;
}

/* ═══════════════════════════════════════════════════════════════════════════
 * display_render — Dibuja todo el estado en LCD (170×320) y OLED (128×64)
 *
 * Layout LCD (vertical, de arriba hacia abajo):
 *   y=  4  Fecha y hora local
 *   y= 20  IP de Wi-Fi o dirección del AP de configuración
 *   x=149  Anillo pequeño MM:SS en el extremo derecho de la cabecera
 *   y= 36  BATERIA + voltaje
 *   y= 46  Separador
 *   y= 52  TEMPERATURA + valor  /  HUMEDAD + valor
 *   y= 68  Separador
 *   y= 76  GPS: estado, LAT, LON
 *   y=104  Separador
 *   y=110  CLIMA: resumen, T actual, min/max, lluvia %
 *   y=158  Presión y fase lunar
 *   y=188  Intervalo entre actualizaciones
 *   y=220  Logger del sistema
 *
 * Layout OLED (128×64, 8 filas de 8 px):
 *   0  Wi-Fi
 *   8  BAT x.xxV
 *  16  T xx.xC  H xx%
 *  24  LAT / LON  (4 decimales)
 *  32  GPS: FIX o BUSCANDO
 *  40  Clima resumen + temp
 *  48  MIN/MAX/P%
 *  56  UPDATE xxs  MM:SS
 * ═══════════════════════════════════════════════════════════════════════════ */

/* Colores del tema oscuro */
#define C_TITLE rgb565(180, 220, 255)  /* Azul claro  */
#define C_LABEL rgb565(80, 190, 200)   /* Cian        */
#define C_VALUE rgb565(230, 230, 230)  /* Blanco suave */
#define C_OK rgb565(50, 210, 100)      /* Verde        */
#define C_WARN rgb565(255, 185, 0)     /* Amarillo     */
#define C_ERR rgb565(230, 60, 60)      /* Rojo         */
#define C_DIM rgb565(42, 58, 67)       /* Gris oscuro  */
#define C_WEATHER rgb565(255, 145, 20) /* Naranja      */

void display_render(display_t *display, const monitor_data_t *data, uint32_t now_ms) {
    char text[48];
    const int remaining = monitor_seconds_until_refresh(data, esp_timer_get_time());

    /* ── LCD ────────────────────────────────────────────────────────────── */
    const uint8_t mask = data->display_fields_mask;

    /* Título */
    time_t epoch = time(NULL);
    struct tm local_time;
    if (epoch > 1700000000 && localtime_r(&epoch, &local_time))
        strftime(text, sizeof(text), "%a %d %b %H:%M", &local_time);
    else
        snprintf(text, sizeof(text), "TIME SYNCING");
    lcd_draw_text(display, text, 4, 4, C_TITLE);

    /* Keep the date and IP together in the top status band. */
    if (data->wifi_connected) {
        snprintf(text, sizeof(text), "IP %.15s", data->ip_address);
        lcd_draw_text(display, text, 4, 20, C_OK);
    } else {
        lcd_draw_text(display, "IP 192.168.4.1", 4, 20, C_WARN);
    }

    /* Batería */
    if (mask & DISPLAY_FIELD_BATTERY) {
        lcd_draw_text(display, "BAT", 4, 36, C_LABEL);
        snprintf(text, sizeof(text), "%.2fV", data->battery_voltage);
        lcd_draw_text(display, text, 28, 36, data->battery_voltage > 3.5f ? C_OK : C_WARN);
    }
    lcd_draw_hline(display, 46, C_DIM);
    /* Upper-right countdown ring shares the date/IP status band. */
    const int ring_cx = LCD_WIDTH - 21;
    lcd_draw_refresh_ring(display, ring_cx, 23, 20, remaining,
                          data->sensor_interval_seconds);
    if (remaining >= 0) snprintf(text, sizeof(text), "%02d:%02d", remaining / 60, remaining % 60);
    else snprintf(text, sizeof(text), "--:--");
    for (size_t i = 0; text[i]; ++i)
        lcd_draw_char(display, text[i], ring_cx - 15 + (int)i * 6, 19, C_VALUE, 0x0000);

    /* Temperatura y Humedad */
    if (mask & DISPLAY_FIELD_DHT) {
        lcd_draw_text(display, "TEMP", 4, 52, C_LABEL);
        if (data->dht_valid) {
            snprintf(text, sizeof(text), "%.1fC", data->temperature_c);
            lcd_draw_text(display, text, 34, 52, C_VALUE);
            lcd_draw_text(display, "HUM", 82, 52, C_LABEL);
            snprintf(text, sizeof(text), "%.0f%%", data->humidity_percent);
            lcd_draw_text(display, text, 106, 52, C_VALUE);
        } else {
            lcd_draw_text(display, "DHT22 SIN DATOS", 34, 52, C_WARN);
        }
    }
    lcd_draw_hline(display, 62, C_DIM);

    /* GPS */
    if (mask & DISPLAY_FIELD_GPS) {
        lcd_draw_text(display, "GPS", 4, 68, C_LABEL);
        if (data->gps_fix) {
            lcd_draw_text(display, "GPS FIX", 28, 68, C_OK);
            snprintf(text, sizeof(text), "LAT %.5f", data->latitude);
            lcd_draw_text(display, text, 4, 80, C_VALUE);
            snprintf(text, sizeof(text), "LON %.5f", data->longitude);
            lcd_draw_text(display, text, 4, 92, C_VALUE);
        } else {
            lcd_draw_text(display, "BUSCANDO SENAL", 28, 68, C_WARN);
            lcd_draw_text(display, "LAT ---.-----", 4, 80, C_DIM);
            lcd_draw_text(display, "LON ---.-----", 4, 92, C_DIM);
        }
    }
    lcd_draw_hline(display, 104, C_DIM);

    /* Clima */
    if (mask & DISPLAY_FIELD_WEATHER) {
        lcd_draw_text(display, "CLIMA", 4, 110, C_LABEL);
        if (data->weather.valid) {
            snprintf(text, sizeof(text), "%-14s %.1fC", data->weather.summary,
                     data->weather.current_temperature_c);
            lcd_draw_text(display, text, 4, 122, C_WEATHER);
            snprintf(text, sizeof(text), "MIN %.1f  MAX %.1fC", data->weather.minimum_temperature_c,
                     data->weather.maximum_temperature_c);
            lcd_draw_text(display, text, 4, 134, C_VALUE);
            snprintf(text, sizeof(text), "LLUVIA %d%%", data->weather.precipitation_probability);
            lcd_draw_text(display, text, 4, 146, C_WARN);
        } else {
            lcd_draw_text(display,
                          data->wifi_connected ? "ESPERANDO GPS/CLIMA" : "ESPERANDO WIFI/GPS", 4,
                          122, C_DIM);
            lcd_draw_text(display, "MIN --  MAX --  P --", 4, 134, C_DIM);
        }
    }
    if (mask & DISPLAY_FIELD_PRESSURE) {
        snprintf(text, sizeof(text), "PRESS %.1f hPa", data->pressure_hpa);
        lcd_draw_text(display, data->bmp280_valid ? text : "PRESS -- hPa", 4, 158,
                      data->bmp280_valid ? C_OK : C_DIM);
    }
    if (mask & DISPLAY_FIELD_MOON) {
        const char *phase = !data->moon_phase_valid ? "--" :
                            data->moon_phase < 0.035f || data->moon_phase >= 0.965f ? "NEW" :
                            data->moon_phase < 0.22f ? "WAX CRES" :
                            data->moon_phase < 0.28f ? "FIRST Q" :
                            data->moon_phase < 0.47f ? "WAX GIB" :
                            data->moon_phase < 0.53f ? "FULL" :
                            data->moon_phase < 0.72f ? "WAN GIB" :
                            data->moon_phase < 0.78f ? "LAST Q" : "WAN CRES";
        snprintf(text, sizeof(text), "MOON %s %d%%", phase,
                 data->moon_illumination_percent);
        lcd_draw_text(display, text, 4, 170, C_WEATHER);
        lcd_draw_moon_icon(display, LCD_WIDTH - 16, 171, data->moon_phase,
                           data->moon_phase_valid);
    }
    lcd_draw_hline(display, 182, C_DIM);

    /* Sensor update interval; remaining time is in the upper-right ring. */
    lcd_draw_text(display, "UPDATE", 4, 188, C_LABEL);
    snprintf(text, sizeof(text), "%us", (unsigned)data->sensor_interval_seconds);
    lcd_draw_text(display, text, 52, 188, C_VALUE);
    lcd_draw_hline(display, 216, C_DIM);
    lcd_draw_text(display, "SYSTEM LOG", 4, 220, C_LABEL);
    for (uint8_t i = 0; i < data->event_log_count && i < 3; ++i)
        lcd_draw_text(display, data->event_log[i], 4, 232 + i * 10, C_VALUE);

    /* ── OLED ───────────────────────────────────────────────────────────── */
    memset(display->oled_buffer, 0, sizeof(display->oled_buffer));

    /* Línea 0 — Wi-Fi */
    if (epoch > 1700000000 && localtime_r(&epoch, &local_time))
        strftime(text, sizeof(text), "%a %d %b %H:%M", &local_time);
    else snprintf(text, sizeof(text), "TIME SYNCING");
    oled_text(display, text, 0, 0);

    /* Línea 1 — Batería */
    snprintf(text, sizeof(text), "IP %.15s", data->wifi_connected ? data->ip_address : "AP 192.168.4.1");
    oled_text(display, text, 0, 8);

    /* Línea 2 — Temperatura y Humedad */
    if (mask & DISPLAY_FIELD_DHT) {
        if (data->dht_valid) {
            snprintf(text, sizeof(text), "T %.1fC H %.0f%%", data->temperature_c,
                     data->humidity_percent);
        } else {
            snprintf(text, sizeof(text), "DHT22 SIN DATOS");
        }
        oled_text(display, text, 0, 16);
    }

    snprintf(text, sizeof(text), "P %.0fhPa", data->pressure_hpa);
    oled_text(display, data->bmp280_valid ? text : "P -- hPa", 0, 24);
    /* Líneas 3-4 — GPS */
    if (mask & DISPLAY_FIELD_GPS) {
        if (data->gps_fix) {
            snprintf(text, sizeof(text), "LAT %.4f", data->latitude);
            oled_text(display, text, 0, 32);
            snprintf(text, sizeof(text), "LON %.4f", data->longitude);
            oled_text(display, text, 0, 40);
        } else {
            oled_text(display, "GPS BUSCANDO", 0, 32);
            oled_text(display, "LAT/LON --", 0, 40);
        }
    }
    if (mask & DISPLAY_FIELD_WEATHER) {
        if (data->weather.valid)
            snprintf(text, sizeof(text), "WX %-8.8s %.0fC", data->weather.summary,
                     data->weather.current_temperature_c);
        else
            snprintf(text, sizeof(text), "WEATHER WAITING");
        oled_text(display, text, 0, 48);
    }

    /* Líneas 5-6 — Clima */
    if (mask & DISPLAY_FIELD_WEATHER) {
        if (data->weather.valid) {
            snprintf(text, sizeof(text), "%-8s %.0fC", data->weather.summary,
                     data->weather.current_temperature_c);
            oled_text(display, text, 0, 40);
            snprintf(
                text, sizeof(text), "%-3d/%-3dC P%d%%", (int)data->weather.minimum_temperature_c,
                (int)data->weather.maximum_temperature_c, data->weather.precipitation_probability);
            oled_text(display, text, 0, 48);
        } else {
            oled_text(display, "CLIMA SIN DATOS", 0, 40);
            oled_text(display, "MIN -- MAX --", 0, 48);
        }
    }

    /* Línea 7 — Intervalo de update + countdown */
    if (remaining >= 0) {
        snprintf(text, sizeof(text), "UPD %us  %02d:%02d", (unsigned)data->sensor_interval_seconds,
                 remaining / 60, remaining % 60);
    } else if (!data->wifi_connected) {
        snprintf(text, sizeof(text), "UPD %us  ESP WIFI", (unsigned)data->sensor_interval_seconds);
    } else {
        snprintf(text, sizeof(text), "UPD %us  ESP GPS", (unsigned)data->sensor_interval_seconds);
    }
    oled_text(display, text, 0, 56);

    oled_flush(display);
}
