// C interface to Nav2 Jazzy's unmodified planar docking control law.
#include <cmath>
#include "nav2_graceful_controller/smooth_control_law.hpp"

extern "C" int explorer_nav2_velocity(
    double x, double y, double heading, double *linear, double *angular) {
  if (!linear || !angular || !std::isfinite(x) || !std::isfinite(y) ||
      !std::isfinite(heading) || std::hypot(x, y) < 1e-9) {
    return 0;
  }
  // Defaults declared in opennav_docking/src/controller.cpp at the pinned revision.
  static nav2_graceful_controller::SmoothControlLaw law(
      3.0, 2.0, 0.4, 2.0, 0.25, 0.1, 0.25, 0.75);
  geometry_msgs::msg::Pose target, current;
  current.orientation.w = 1.0;
  target.position.x = x;
  target.position.y = y;
  target.orientation.z = std::sin(heading / 2.0);
  target.orientation.w = std::cos(heading / 2.0);
  const auto command = law.calculateRegularVelocity(target, current, false);
  *linear = command.linear.x;
  *angular = command.angular.z;
  return std::isfinite(*linear) && std::isfinite(*angular);
}
