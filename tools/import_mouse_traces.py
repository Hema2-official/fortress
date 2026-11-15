#!/usr/bin/env python3
"""Curate normalized spatial traces; discard timestamps, IDs and screen metadata."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


def curate(records, count=64, points=24):
    selected = []
    for record in records:
        raw = record.get("trajectory", [])
        if record.get("type") != 0 or len(raw) < points:
            continue
        if not all(len(p) == 2 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in p) for p in raw):
            continue
        sx, sy = raw[0]
        dx, dy = raw[-1][0] - sx, raw[-1][1] - sy
        length2 = dx * dx + dy * dy
        if not 80**2 <= length2 <= 1400**2:
            continue
        trajectory = []
        for i in range(points):
            x, y = raw[round(i * (len(raw) - 1) / (points - 1))]
            x, y = x - sx, y - sy
            trajectory.append([round((x * dx + y * dy) / length2, 6),
                               round((y * dx - x * dy) / length2, 6)])
        if any(not -0.25 <= x <= 1.25 or abs(y) > 0.35 for x, y in trajectory):
            continue
        trajectory[0], trajectory[-1] = [0.0, 0.0], [1.0, 0.0]
        selected.append(trajectory)
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError(f"only {len(selected)} usable mouse trajectories")
    return selected


def header(trajectories):
    rows = []
    for trajectory in trajectories:
        points = ", ".join("{" + f"{x:.6f}, {y:.6f}" + "}" for x, y in trajectory)
        rows.append("    {{" + points + "}},")
    return '''// Spatial samples derived from Jason's MIT-licensed cursor dataset.
// Attribution and provenance: THIRD_PARTY_MOUSE_NOTICE and mouse-provenance.json.
// Point timing below is independently synthesized, not recorded human timing.
#ifndef CONTENT_BROWSER_DEVTOOLS_PROTOCOL_UXR_MOUSE_TRAJECTORIES_H_
#define CONTENT_BROWSER_DEVTOOLS_PROTOCOL_UXR_MOUSE_TRAJECTORIES_H_
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>
namespace content::protocol::uxr_mouse {
struct Point { double x; double y; int offset_ms; };
struct ShapePoint { double u; double v; };
inline constexpr std::array<std::array<ShapePoint, 24>, 64> kShapes = {{
''' + "\n".join(rows) + '''
}};
inline std::vector<Point> MakeTrajectory(double sx, double sy, double ex,
                                        double ey, uint64_t selector) {
  std::vector<Point> result;
  const double dx = ex - sx, dy = ey - sy;
  const double distance = std::hypot(dx, dy);
  if (!std::isfinite(distance) || distance < 8.0 || distance > 20000.0)
    return result;
  const int duration = std::clamp(
      static_cast<int>(80.0 + 45.0 * std::log2(1.0 + distance / 12.0)), 90, 450);
  const auto& shape = kShapes[selector % kShapes.size()];
  for (size_t i = 1; i < shape.size(); ++i) {
    result.push_back({sx + dx * shape[i].u - dy * shape[i].v,
                      sy + dy * shape[i].u + dx * shape[i].v,
                      static_cast<int>(i * duration / (shape.size() - 1))});
  }
  result.back().x = ex;
  result.back().y = ey;
  return result;
}
}  // namespace content::protocol::uxr_mouse
#endif
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    data = args.input.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.expected_sha256:
        raise ValueError("source dataset checksum mismatch")
    args.output.write_text(header(curate(json.loads(data))))


if __name__ == "__main__":
    main()
