#!/usr/bin/env python3
"""In thong tin /<ns>/scan va khoang cach gan nhat theo 4 huong (truoc, trai, sau, phai).
Dung de kiem tra lidar co hoat dong va co bi chinh than xe/tay chan khong."""
import math
import sys

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

NS = sys.argv[1] if len(sys.argv) > 1 else "robot1"


class ScanCheck(Node):
    def __init__(self):
        super().__init__("scan_check")
        self.n = 0
        self.create_subscription(LaserScan, f"/{NS}/scan", self.cb, 10)

    def cb(self, m: LaserScan):
        self.n += 1
        if self.n > 3:
            rclpy.shutdown()
            return
        sectors = {"truoc": (-30, 30), "trai": (60, 120), "sau": (150, 210), "phai": (-120, -60)}
        best = {k: float("inf") for k in sectors}
        valid = 0
        for i, r in enumerate(m.ranges):
            if not math.isfinite(r) or r < m.range_min or r > m.range_max:
                continue
            valid += 1
            a = math.degrees(m.angle_min + i * m.angle_increment)
            a = (a + 180.0) % 360.0 - 180.0
            for k, (lo, hi) in sectors.items():
                aa = a if lo >= -180 and hi <= 180 else a
                if (lo <= aa <= hi) or (lo <= aa + 360 <= hi):
                    best[k] = min(best[k], r)
        print("SCAN frame_id=%s so_tia=%d hop_le=%d range_min=%.3f range_max=%.1f goc=[%.0f, %.0f] do"
              % (m.header.frame_id, len(m.ranges), valid, m.range_min, m.range_max,
                 math.degrees(m.angle_min), math.degrees(m.angle_max)))
        print("SCAN gan nhat (m):", {k: (round(v, 2) if v != float("inf") else None) for k, v in best.items()})


def main():
    rclpy.init()
    node = ScanCheck()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
