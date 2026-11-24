// ESP32-S3 desktop enclosure: landscape ILI9488, OLED, two rear solar panels.
// Millimetres. Solar footprint: Steren PS-003, 56 x 60 x 3 mm.
part = "visual"; // [visual,assembly,front,back,base,side,solar_clip]

case_w = 190;
face_h = 110;
face_t = 3;
base_depth = 100;
base_t = 3;
back_t = 3;
cheek_t = 14;
front_angle = 18;
front_bottom_z = 9;
m3_clearance = 3.4;
m3_insert_bore = 4.2; // check chosen heat-set insert
m2_clearance = 2.5;
mount_x = 7;

// Reference SPI PCB 98 x 56.34; visible area 73.44 x 48.96; hole pitch 92 x 49.5.
lcd_pcb_w = 98;
lcd_pcb_h = 56.34;
lcd_active_w = 73.44;
lcd_active_h = 48.96;
lcd_hole_dx = 92;
lcd_hole_dy = 49.5;
front_group_offset = (case_w-190)/2;
lcd_x = 16+front_group_offset;
lcd_y = (face_h-lcd_pcb_h)/2;
lcd_window_margin = 0.5;
oled_window_w = 27;
oled_window_h = 20;
oled_x = 142+front_group_offset;
oled_y = (face_h-oled_window_h)/2;

// Steren PS-003 panel dimensions supplied for the two rear positions.
solar_w = 56;
solar_h = 60;
solar_t = 3;
solar_gap = 10;
solar_y = (face_h-solar_h)/2;
solar_left_x = (case_w-(2*solar_w+solar_gap))/2;
solar_right_x = solar_left_x+solar_w+solar_gap;
clip_w = 16;
clip_h = 10;

back_y = base_depth;
front_top_y = face_h*sin(front_angle);
front_top_z = front_bottom_z+face_h*cos(front_angle);

assert(case_w >= 190, "Front display layout needs at least 190 mm of width");
assert(case_w >= 2*solar_w+solar_gap+20, "Two solar panels need a wider case");
assert(face_h >= solar_h+20, "Solar panels need a taller rear plate");
assert(cheek_t == 2*mount_x, "Side fasteners must be centered in the cheeks");
assert(lcd_x+lcd_pcb_w+8 < oled_x, "LCD and OLED PCB envelopes overlap");
assert(oled_x+oled_window_w < case_w-cheek_t, "OLED needs side clearance");

module front_pose() {
  translate([0,0,front_bottom_z]) rotate([90-front_angle,0,0]) children();
}
// Local +Z is the exterior of the rear plate.
module back_pose() {
  translate([0,back_y,front_top_z]) rotate([-90,0,0]) children();
}
module lcd_holes() {
  for (x=[lcd_x+(lcd_pcb_w-lcd_hole_dx)/2,
          lcd_x+(lcd_pcb_w+lcd_hole_dx)/2])
    for (y=[lcd_y+(lcd_pcb_h-lcd_hole_dy)/2,
            lcd_y+(lcd_pcb_h+lcd_hole_dy)/2])
      translate([x,y,0]) children();
}

module front_panel() {
  difference() {
    union() {
      cube([case_w,face_h,face_t]);
      lcd_holes() translate([0,0,-5]) cylinder(h=5,d=7,$fn=32);
    }
    for (x=[mount_x,case_w-mount_x])
      for (y=[12,face_h-12])
        translate([x,y,-6]) cylinder(h=face_t+12,d=m3_clearance,$fn=32);
    translate([lcd_x+(lcd_pcb_w-lcd_active_w)/2-lcd_window_margin,
               lcd_y+(lcd_pcb_h-lcd_active_h)/2-lcd_window_margin,-1])
      cube([lcd_active_w+2*lcd_window_margin,
            lcd_active_h+2*lcd_window_margin,face_t+2]);
    translate([oled_x,oled_y,-1])
      cube([oled_window_w,oled_window_h,face_t+2]);
    lcd_holes() translate([0,0,-6]) cylinder(h=face_t+12,d=2.8,$fn=32);
    // Slotted OLED straps accommodate different SSD1306 PCB patterns.
    for (x=[oled_x-5,oled_x+oled_window_w+5])
      for (y=[oled_y+2,oled_y+oled_window_h-2])
        translate([x,y,-1]) hull() {
          translate([0,-2,0]) cylinder(h=face_t+2,d=2.6,$fn=20);
          translate([0, 2,0]) cylinder(h=face_t+2,d=2.6,$fn=20);
        }
  }
}

module clip_positions() {
  for (x=[solar_left_x-5,
          solar_left_x+solar_w+solar_gap/2,
          solar_right_x+solar_w+5])
    for (y=[solar_y+13,solar_y+solar_h-13])
      translate([x,y,0]) children();
}
module back_panel() {
  difference() {
    cube([case_w,face_h,back_t]);
    for (x=[mount_x,case_w-mount_x])
      for (y=[12,face_h-12])
        translate([x,y,-1]) cylinder(h=back_t+2,d=m3_clearance,$fn=32);
    clip_positions() translate([0,0,-1])
      cylinder(h=back_t+2,d=m2_clearance,$fn=24);
    for (x=[solar_left_x+solar_w/2,solar_right_x+solar_w/2])
      translate([x,solar_y+solar_h-6,-1])
        cylinder(h=back_t+2,d=6,$fn=32);
    for (x=[48:16:144])
      translate([x,6,-1]) cube([5,5,back_t+2]);
  }
}

module base_panel() {
  difference() {
    cube([case_w,base_depth,base_t]);
    for (x=[mount_x,case_w-mount_x])
      for (y=[12,base_depth-12])
        translate([x,y,-1]) cylinder(h=base_t+2,d=m3_clearance,$fn=32);
    translate([case_w/2-12,base_depth-18,-1])
      cube([24,9,base_t+2]);
    for (x=[case_w/2-34,case_w/2+34])
      for (y=[38,61])
        translate([x,y,-1]) cube([3,10,base_t+2]);
  }
}

// Left cheek occupies X=0..cheek_t; print two copies.
module side_cheek() {
  difference() {
    multmatrix([[0,0,1,0],[1,0,0,0],[0,1,0,0],[0,0,0,1]])
      linear_extrude(height=cheek_t)
        polygon([[0,base_t],[back_y,base_t],[back_y,front_top_z],
                 [front_top_y,front_top_z],[0,front_bottom_z]]);
    // Insert bores are coaxial with the front, rear and base clearance holes.
    front_pose() for (y=[12,face_h-12])
      translate([mount_x,y,-8])
        cylinder(h=9,d=m3_insert_bore,$fn=32);
    back_pose() for (y=[12,face_h-12])
      translate([mount_x,y,-8])
        cylinder(h=9,d=m3_insert_bore,$fn=32);
    for (y=[12,base_depth-12])
      translate([mount_x,y,base_t])
        cylinder(h=8,d=m3_insert_bore,$fn=32);
  }
}

module solar_clip() {
  difference() {
    union() {
      translate([-clip_w/2,-clip_h/2,solar_t])
        cube([clip_w,clip_h,3]);
      cylinder(h=solar_t,d=5,$fn=24);
    }
    translate([0,0,-1]) cylinder(h=solar_t+5,d=m2_clearance,$fn=24);
  }
}

module assembled() {
  color("#3c424b") front_pose() front_panel();
  color("#424852") back_pose() back_panel();
  color("#303844") base_panel();
  color("#343b45") side_cheek();
  color("#343b45") translate([case_w,0,0]) mirror([1,0,0]) side_cheek();
  back_pose() clip_positions() color("#aab6c7")
    translate([0,0,back_t]) solar_clip();
}

module solar_visual(x) {
  color("#101d35") translate([x,solar_y,back_t+0.15])
    cube([solar_w,solar_h,solar_t]);
  for (col=[0:4], row=[0:3])
    color("#345a92")
      translate([x+3+col*(solar_w-6)/5,
                 solar_y+3+row*(solar_h-6)/4,
                 back_t+solar_t+0.16])
        cube([(solar_w-6)/5-1,(solar_h-6)/4-1,0.2]);
}

module visual() {
  assembled();
  front_pose() {
    color("#164a6b") translate([lcd_x+(lcd_pcb_w-lcd_active_w)/2,
                                 lcd_y+(lcd_pcb_h-lcd_active_h)/2,-0.5])
      cube([lcd_active_w,lcd_active_h,0.6]);
    color("#0f5662") translate([oled_x,oled_y,-0.5])
      cube([oled_window_w,oled_window_h,0.6]);
  }
  back_pose() {
    solar_visual(solar_left_x);
    solar_visual(solar_right_x);
  }
}

if (part == "visual") visual();
if (part == "assembly") assembled();
if (part == "front") translate([0,0,face_t]) mirror([0,0,1]) front_panel();
if (part == "back") back_panel();
if (part == "base") base_panel();
if (part == "side")
  multmatrix([[0,1,0,0],[0,0,1,-base_t],[1,0,0,0],[0,0,0,1]])
    side_cheek();
if (part == "solar_clip")
  translate([0,0,solar_t+3]) mirror([0,0,1]) solar_clip();
