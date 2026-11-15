#include <cassert>
#include <cmath>
#include <limits>
#include "uxr_mouse_trajectories.h"
int main() {
  using content::protocol::uxr_mouse::MakeTrajectory;
  assert(MakeTrajectory(0, 0, 2, 2, 0).empty());
  assert(MakeTrajectory(0, 0, std::numeric_limits<double>::infinity(), 0, 0).empty());
  for (unsigned seed = 0; seed < 128; ++seed) {
    auto path = MakeTrajectory(10, 20, 400, 600, seed);
    assert(path.size() == 23);
    int previous = 0;
    for (const auto& point : path) {
      assert(std::isfinite(point.x) && std::isfinite(point.y));
      assert(point.offset_ms > previous && point.offset_ms <= 450);
      previous = point.offset_ms;
    }
    assert(path.back().x == 400 && path.back().y == 600);
    auto vertical = MakeTrajectory(20, 30, 20, 630, seed);
    assert(vertical.back().x == 20 && vertical.back().y == 630);
    auto reverse = MakeTrajectory(400, 600, 10, 20, seed);
    assert(reverse.back().x == 10 && reverse.back().y == 20);
  }
}
