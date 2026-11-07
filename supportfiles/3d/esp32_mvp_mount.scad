// ESP32 telemetry MVP angled desktop enclosure.
// Units: mm. Export each part separately by changing `part`.
part = "assembly"; // [assembly, front, back, side]

panel_w = 145;
panel_h = 92;
panel_t = 3;
lcd_window_w = 24;
lcd_window_h = 44;
oled_window_w = 27;
oled_window_h = 20;
corner_offset = 7;
m3_clearance = 3.4;
view_angle = 18;
depth = 82;
cheek_t = 4;

module front_panel() {
  difference() {
    cube([panel_w, panel_h, panel_t]);
    // M3 panel-to-cheek fasteners, two at each side.
    for (y = [14, panel_h-14])
      for (x = [corner_offset, panel_w-corner_offset])
        translate([x,y,-1]) cylinder(h=panel_t+2,d=m3_clearance,$fn=32);
    // Color LCD window (portrait module, left of the OLED).
    translate([22, (panel_h-lcd_window_h)/2, -1])
      cube([lcd_window_w,lcd_window_h,panel_t+2]);
    // OLED window.
    translate([79, (panel_h-oled_window_h)/2, -1])
      cube([oled_window_w,oled_window_h,panel_t+2]);
    // Four flexible retention slots; adjust after measuring the PCBs.
    for (p = [[18,20],[51,20],[18,72],[51,72],[75,31],[110,31],[75,61],[110,61]])
      translate([p[0],p[1],-1]) hull() {
        translate([-2,0,0]) cylinder(h=panel_t+2,d=3.2,$fn=24);
        translate([ 2,0,0]) cylinder(h=panel_t+2,d=3.2,$fn=24);
      }
  }
}

module rear_plate() {
  difference() {
    cube([panel_w,depth,3]);
    // Cable exit and ventilation slots.
    translate([panel_w/2-15,-1,1]) cube([30,10,4]);
    for (x=[45:10:100]) translate([x,depth-15,-1]) cube([4,10,5]);
    // Four M3 fasteners joining rear plate to side cheeks.
    for (x=[corner_offset,panel_w-corner_offset])
      for (y=[12,depth-12])
        translate([x,y,-1]) cylinder(h=5,d=m3_clearance,$fn=32);
  }
}

module side_cheek() {
  // Side profile lies in the Y-Z plane. Its sloped edge follows the tilted face.
  // Local X maps to world Y, local Y to world Z, and extrusion to world X.
  rotate([0,0,90]) rotate([90,0,0]) linear_extrude(height=cheek_t)
    difference() {
      polygon([[0,0],[depth,0],[depth,14],[28.4,118],[0,31]]);
      // M3 bracket holes: two at the front-panel edge and two at the base.
      for (p=[[7.3,43.3],[27,104.2],[12,7],[70,7]])
        translate(p) circle(d=m3_clearance,$fn=32);
    }
}

module assembled() {
  // Front plate stands 18 degrees back from vertical, seated at the cheek edge.
  translate([0,0,31]) rotate([90-view_angle,0,0]) front_panel();
  translate([0,0,0]) rear_plate();
  translate([0,0,0]) side_cheek();
  translate([panel_w-cheek_t,0,0]) side_cheek();
}

if (part == "assembly") assembled();
if (part == "front") front_panel();
if (part == "back") rear_plate();
if (part == "side") side_cheek();
