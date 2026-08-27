// SPDX-License-Identifier: LGPL-2.1-or-later

#include "MbDMassMarker.h"

#include <App/GeoFeatureGroupExtension.h>
#include <Base/Exception.h>
#include <Base/Quantity.h>
#include <Mod/Material/App/MaterialManager.h>
#include <QString>
#include <QVariant>

#include <exception>
#include <memory>

#include "MbDPart.h"

PROPERTY_SOURCE(MbDFEM::MbDMassMarker, MbDFEM::MbDMarker)

namespace
{

constexpr auto CalculixSteelUuid = "92589471-a6cb-4bbc-b748-d425a17dea7d";

std::shared_ptr<Materials::Material> defaultMassMarkerMaterial()
{
    auto material = Materials::MaterialManager::getManager().getMaterial(
        QString::fromLatin1(CalculixSteelUuid));
    if (material) {
        return material;
    }

    return Materials::MaterialManager::defaultMaterial();
}

double materialDensity(const Materials::Material& material, const char* unit, double fallback)
{
    if (!material.hasPhysicalProperty(QStringLiteral("Density"))) {
        return fallback;
    }

    const QVariant density = material.getPhysicalValue(QStringLiteral("Density"));
    if (!density.isValid() || density.isNull()) {
        return fallback;
    }

    const Base::Quantity target(1.0, unit);
    if (density.canConvert<Base::Quantity>()) {
        const Base::Quantity quantity = density.value<Base::Quantity>();
        if (quantity.isValid()) {
            return quantity.getValueAs(target);
        }
    }

    bool ok = false;
    const double numericDensity = density.toDouble(&ok);
    if (ok) {
        return numericDensity;
    }

    try {
        const Base::Quantity quantity = Base::Quantity::parse(density.toString().toStdString());
        if (quantity.isValid()) {
            return quantity.getValueAs(target);
        }
    }
    catch (const Base::Exception&) {
    }
    catch (const std::exception&) {
    }

    return fallback;
}

}  // namespace

MbDFEM::MbDMassMarker::MbDMassMarker()
{
    Label.setValue("MassMarker");

    ADD_PROPERTY_TYPE(mass, (1.0), "MbDFEM", App::Prop_None, "Mass of this part");
    ADD_PROPERTY_TYPE(principalInertias,
                      (Base::Vector3d(1.0, 1.0, 1.0)),
                      "MbDFEM",
                      App::Prop_None,
                      "Principal moments of inertia ordered along marker X, Y, and Z axes");
    ADD_PROPERTY_TYPE(massMarkerFromShape,
                      (false),
                      "MbDFEM",
                      App::Prop_None,
                      "True when this mass marker was populated from its part's shape mass properties");
    auto mat = defaultMassMarkerMaterial();
    ADD_PROPERTY_TYPE(material, (*mat), "MbDFEM", App::Prop_None, "Material of this part");
}

double MbDFEM::MbDMassMarker::densityInKgPerMm3() const
{
    return materialDensity(material.getValue(), "kg/mm^3", 1.0);
}

double MbDFEM::MbDMassMarker::densityInKgPerM3() const
{
    return materialDensity(material.getValue(), "kg/m^3", 1.0e9);
}

void MbDFEM::MbDMassMarker::onChanged(const App::Property* prop)
{
    MbDMarker::onChanged(prop);

    if (isRestoring()) {
        return;
    }

    if (prop != &mass && prop != &principalInertias && prop != &material && prop != &Placement) {
        return;
    }

    auto* part = freecad_cast<MbDFEM::MbDPart*>(
        App::GeoFeatureGroupExtension::getGroupOfObject(this));
    if (part && part->getMassMarker() == this) {
        if (prop == &material && massMarkerFromShape.getValue()) {
            try {
                part->populateMassMarkerFromShape();
            }
            catch (const Base::Exception&) {
                massMarkerFromShape.setValue(false);
            }
        }
        else if (prop != &massMarkerFromShape) {
            massMarkerFromShape.setValue(false);
        }
    }
}
