//! Small in-memory grayscale BMP renderer for the current lunar phase.

const WIDTH: usize = 64;
const HEADER_SIZE: usize = 1078;

pub fn render_bmp(mut phase: f32) -> Vec<u8> {
    let mut buffer = vec![0; HEADER_SIZE + WIDTH * WIDTH];
    let file_size = buffer.len() as u32;
    buffer[0..2].copy_from_slice(b"BM");
    buffer[2..6].copy_from_slice(&file_size.to_le_bytes());
    buffer[10..14].copy_from_slice(&(HEADER_SIZE as u32).to_le_bytes());
    buffer[14..18].copy_from_slice(&40u32.to_le_bytes());
    buffer[18..22].copy_from_slice(&(WIDTH as u32).to_le_bytes());
    buffer[22..26].copy_from_slice(&(WIDTH as u32).to_le_bytes());
    buffer[26..28].copy_from_slice(&1u16.to_le_bytes());
    buffer[28..30].copy_from_slice(&8u16.to_le_bytes());
    buffer[34..38].copy_from_slice(&((WIDTH * WIDTH) as u32).to_le_bytes());
    buffer[46..50].copy_from_slice(&256u32.to_le_bytes());
    for value in 0..=255usize {
        let offset = 54 + value * 4;
        buffer[offset..offset + 3].fill(value as u8);
    }

    if !phase.is_finite() {
        phase = 0.0;
    }
    phase = phase.rem_euclid(1.0);
    let angle = phase * std::f32::consts::TAU;
    let (sun_x, sun_z) = (angle.sin(), -angle.cos());
    let center = (WIDTH - 1) as f32 * 0.5;
    let radius = 28.5f32;
    let craters = [
        (-0.35f32, -0.30f32, 0.12f32),
        (0.30, -0.42, 0.09),
        (0.42, 0.12, 0.14),
        (-0.22, 0.36, 0.10),
        (0.02, -0.04, 0.08),
        (-0.48, 0.12, 0.07),
    ];

    for y in 0..WIDTH {
        for x in 0..WIDTH {
            let nx = (x as f32 - center) / radius;
            let ny = (y as f32 - center) / radius;
            let r2 = nx * nx + ny * ny;
            if r2 > 1.0 {
                continue;
            }
            let nz = (1.0 - r2).sqrt();
            let light = nx * sun_x + nz * sun_z;
            let noise = (nx * 31.0 + ny * 19.0).sin() * 4.0 + (nx * 17.0 - ny * 29.0).cos() * 3.0;
            let mut surface = if light > 0.0 {
                176.0 + nz * 14.0 + noise
            } else {
                14.0 + noise * 0.15
            };
            for (cx, cy, crater_r) in craters {
                let dx = nx - cx;
                let dy = ny - cy;
                let d2 = dx * dx + dy * dy;
                if d2 < crater_r * crater_r {
                    surface += if d2.sqrt() / crater_r > 0.78 {
                        18.0
                    } else {
                        -22.0
                    };
                }
            }
            let offset = HEADER_SIZE + (WIDTH - 1 - y) * WIDTH + x;
            buffer[offset] = surface.clamp(0.0, 255.0) as u8;
        }
    }
    buffer
}
