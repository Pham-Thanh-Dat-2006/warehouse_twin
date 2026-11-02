#!/usr/bin/env python3
"""Doi /<ns>/cmd_vel (theo huong mui xe) thanh van toc 3 khop ao cua Ridgeback
(x, y theo he toa do the gioi, yaw), gui vao Isaac Sim qua /<ns>/joint_command.

Goc yaw lay tu /<ns>/odom. Co gioi han gia toc de xe khong giat, va tu dung
neu qua 0.5 s khong co cmd_vel.
"""
import math
import time
import signal

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool

JOINTS = ["dummy_base_prismatic_x_joint",
          "dummy_base_prismatic_y_joint",
          "dummy_base_revolute_z_joint"]


def clamp_step(cur, target, max_delta):
    d = target - cur
    if d > max_delta:
        return cur + max_delta
    if d < -max_delta:
        return cur - max_delta
    return target


class RidgebackBridge(Node):
    def __init__(self):
        super().__init__("ridgeback_bridge")
        self.declare_parameter("ns", "robot1")
        self.declare_parameter("rate", 50.0)
        self.declare_parameter("max_lin", 1.0)      # m/s
        self.declare_parameter("max_ang", 1.5)      # rad/s
        self.declare_parameter("acc_lin", 1.0)      # m/s^2
        self.declare_parameter("acc_ang", 2.0)      # rad/s^2
        self.declare_parameter("timeout", 0.5)      # s

        self.declare_parameter("motion_gate", False)
        self.declare_parameter("pose_topic", "")
        self.declare_parameter("turn_in_place_angular", 0.0)
        self.declare_parameter("pose_timeout", 1.0)
        self.declare_parameter("pose_sim_timeout", 0.0)
        ns = self.get_parameter("ns").value
        self.use_gate = bool(self.get_parameter("motion_gate").value)
        self.allowed = not self.use_gate
        self.gate_at = 0.0
        self.pose_timeout = float(self.get_parameter("pose_timeout").value)
        self.pose_sim_timeout = float(self.get_parameter("pose_sim_timeout").value)
        self.pose_stamp_ns = None
        self.odom_at = 0.0
        self.turn_threshold = float(self.get_parameter("turn_in_place_angular").value)
        pose_topic = self.get_parameter("pose_topic").value or f"/{ns}/odom"
        self.rate = float(self.get_parameter("rate").value)
        self.max_lin = float(self.get_parameter("max_lin").value)
        self.max_ang = float(self.get_parameter("max_ang").value)
        self.acc_lin = float(self.get_parameter("acc_lin").value)
        self.acc_ang = float(self.get_parameter("acc_ang").value)
        self.timeout = float(self.get_parameter("timeout").value)

        self.yaw = 0.0
        self.have_odom = False
        self.v_cmd = 0.0
        self.w_cmd = 0.0
        self.last_cmd = self.get_clock().now()
        self.v = 0.0        # van toc hien tai da lam muot
        self.w = 0.0

        self.create_subscription(Twist, f"/{ns}/cmd_vel", self.on_cmd, 10)
        self.create_subscription(Odometry, pose_topic, self.on_odom, 10)
        if self.use_gate:
            self.create_subscription(Bool, f"/{ns}/motion_enabled", self.on_gate, 10)
        self.pub = self.create_publisher(JointState, f"/{ns}/joint_command", 10)
        self.create_timer(1.0 / self.rate, self.tick)
        self.get_logger().info(f"ridgeback_bridge: /{ns}/cmd_vel -> /{ns}/joint_command")

    def on_gate(self, msg):
        self.allowed = msg.data
        self.gate_at = time.monotonic()
        if not self.allowed:
            self.v = self.w = 0.0
            self.publish(0.0,0.0,0.0)

    def on_cmd(self, msg: Twist):
        self.v_cmd = max(-self.max_lin, min(self.max_lin, msg.linear.x))
        self.w_cmd = max(-self.max_ang, min(self.max_ang, msg.angular.z))
        self.last_cmd = self.get_clock().now()

    def on_odom(self, msg: Odometry):
        q = msg.pose.pose.orientation
        self.yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                              1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.have_odom = True
        self.odom_at = time.monotonic()
        self.pose_stamp_ns = msg.header.stamp.sec*10**9+msg.header.stamp.nanosec

    def publish(self, vx, vy, w):
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.name = JOINTS
        js.velocity = [float(vx), float(vy), float(w)]
        self.pub.publish(js)

    def tick(self):
        dt = 1.0 / self.rate
        pose_sim_stale = (self.pose_sim_timeout > 0 and self.pose_stamp_ns is not None and
                          (self.get_clock().now().nanoseconds-self.pose_stamp_ns)*1e-9 > self.pose_sim_timeout)
        if ((self.use_gate and (not self.allowed or time.monotonic()-self.gate_at > .5))
                or not self.have_odom or time.monotonic()-self.odom_at > self.pose_timeout or pose_sim_stale):
            self.v = self.w = 0.0
            self.publish(0.0,0.0,0.0)
            return
        age = (self.get_clock().now() - self.last_cmd).nanoseconds * 1e-9
        v_t, w_t = (self.v_cmd, self.w_cmd) if age < self.timeout else (0.0, 0.0)
        if self.turn_threshold > 0 and abs(w_t) >= self.turn_threshold:
            v_t = 0.0
        self.v = clamp_step(self.v, v_t, self.acc_lin * dt)
        self.w = clamp_step(self.w, w_t, self.acc_ang * dt)
        # chua co odom thi khong biet huong mui xe -> khong di chuyen
        if not self.have_odom:
            self.publish(0.0, 0.0, 0.0)
            return
        self.publish(self.v * math.cos(self.yaw), self.v * math.sin(self.yaw), self.w)


def main():
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    def terminate(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    node = RidgebackBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # gui lenh dung truoc khi thoat de xe khong troi di
        node.use_gate = True
        node.allowed = False
        node.v_cmd = node.w_cmd = 0.0
        for _ in range(5):
            node.publish(0.0, 0.0, 0.0)
            rclpy.spin_once(node, timeout_sec=.02)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
