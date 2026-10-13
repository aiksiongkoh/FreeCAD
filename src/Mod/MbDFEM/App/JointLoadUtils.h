// SPDX-License-Identifier: LGPL-2.1-or-later
#pragma once

#include "MbDPart.h"
#include "MbDMarker.h"
#include "MbDAssembly.h"
#include <App/Document.h>
#include <algorithm>
#include <stdexcept>

namespace MbDFEM::JointLoadUtils
{
// Solved joint histories use SI torque; geometry and FEM moment arms use mm.
inline constexpr double siTorqueToFEMTorque = 1000.0;

inline const MbDFEM::MbDPart* markerPart(const MbDFEM::MbDMarker* marker)
{
    if (marker) {
        for (const auto* object : marker->getDocument()->getObjects()) {
            const auto* part = freecad_cast<const MbDFEM::MbDPart*>(object);
            if (part) {
                const auto& markers = part->markers.getValues();
                if (std::find(markers.begin(), markers.end(), marker) != markers.end()) {
                    return part;
                }
            }
        }
    }
    throw std::runtime_error("Joint marker has no owning MbDPart.");
}

inline double sampleValue(const App::PropertyFloatList& series, int index)
{
    const auto& values = series.getValues();
    return values.empty() ? 0.0 : values[std::clamp(index, 0, static_cast<int>(values.size()) - 1)];
}

inline Base::Placement sampledPlacement(const MbDFEM::MbDPart& part, int lower, int upper, double ratio)
{
    Base::Placement result = part.globalPlacement();
    if (lower < 0) {
        return result;
    }
    Base::Placement assemblyPlacement;
    for (const auto* object : part.getDocument()->getObjects()) {
        const auto* assembly = freecad_cast<const MbDFEM::MbDAssembly*>(object);
        if (assembly) {
            const auto contains = [&part](const auto& list) {
                const auto& items = list.getValues();
                return std::find(items.begin(), items.end(), &part) != items.end();
            };
            if (contains(assembly->parts) || contains(assembly->fixedparts)) {
                assemblyPlacement = assembly->globalPlacement();
                break;
            }
        }
    }
    const auto sample = [=](const auto& series) {
        return sampleValue(series, lower) * (1.0 - ratio) + sampleValue(series, upper) * ratio;
    };
    if (!part.xs.getValues().empty() && !part.ys.getValues().empty() && !part.zs.getValues().empty()) {
        Base::Vector3d position(sample(part.xs), sample(part.ys), sample(part.zs));
        assemblyPlacement.multVec(position, position);
        result.setPosition(position);
    }
    if (!part.bryxs.getValues().empty() && !part.bryys.getValues().empty()
        && !part.bryzs.getValues().empty()) {
        const auto rotation = [&part](int index) {
            return Base::Rotation(Base::Vector3d::UnitZ, sampleValue(part.bryzs, index))
                * Base::Rotation(Base::Vector3d::UnitY, sampleValue(part.bryys, index))
                * Base::Rotation(Base::Vector3d::UnitX, sampleValue(part.bryxs, index));
        };
        result.setRotation(
            assemblyPlacement.getRotation()
            * Base::Rotation::slerp(rotation(lower), rotation(upper), ratio)
        );
    }
    return result;
}

}  // namespace MbDFEM::JointLoadUtils
