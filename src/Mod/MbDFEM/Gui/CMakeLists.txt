# SPDX-License-Identifier: LGPL-2.1-or-later

set(MbDFEMGui_LIBS
    MbDFEM
    PartGui
    FreeCADGui
)

if(BUILD_FEM_VTK)
    generate_from_py(ViewProviderFEMPostPipeline)
    list(APPEND MbDFEMGui_LIBS FemGui ${VTK_LIBRARIES})
endif()

set(MbDFEMGui_SRCS
    AppMbDFEMGui.cpp
    ViewProviderFEMAssembly.cpp
    ViewProviderFEMAssembly.h
    ViewProviderFEMItem.cpp
    ViewProviderFEMItem.h
    ViewProviderFEMPart.cpp
    ViewProviderFEMPart.h
    ViewProviderFEMResultsFolder.cpp
    ViewProviderFEMResultsFolder.h
    ViewProviderAxisTriad.cpp
    ViewProviderAxisTriad.h
    ViewProviderUtils.cpp
    ViewProviderUtils.h
    ViewProviderMbDAction.cpp
    ViewProviderMbDAction.h
    ViewProviderMbDAnimationParameters.cpp
    ViewProviderMbDAnimationParameters.h
    ViewProviderMbDAssembly.cpp
    ViewProviderMbDAssembly.h
    ViewProviderMbDItemIJ.cpp
    ViewProviderMbDItemIJ.h
    ViewProviderMbDJoint.cpp
    ViewProviderMbDJoint.h
    ViewProviderMbDGravity.cpp
    ViewProviderMbDGravity.h
    ViewProviderMbDMarker.cpp
    ViewProviderMbDMarker.h
    ViewProviderMbDMotion.cpp
    ViewProviderMbDMotion.h
    ViewProviderMbDPart.cpp
    ViewProviderMbDPart.h
    ViewProviderMbDSimulationParameters.cpp
    ViewProviderMbDSimulationParameters.h
)

if(BUILD_FEM_VTK)
    list(APPEND MbDFEMGui_SRCS
        ViewProviderFEMPostPipeline.cpp
        ViewProviderFEMPostPipeline.h
        ViewProviderFEMPostPipeline.pyi
        ViewProviderFEMPostPipelinePyImp.cpp
    )
endif()

add_library(MbDFEMGui SHARED ${MbDFEMGui_SRCS})

if(BUILD_FEM_VTK)
    target_compile_definitions(MbDFEMGui PRIVATE MBDFEM_WITH_VTK)
    target_include_directories(MbDFEMGui PRIVATE ${VTK_INCLUDE_DIRS})
endif()

target_include_directories(
    MbDFEMGui
    PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_BINARY_DIR}
    ${CMAKE_BINARY_DIR}/src
    ${CMAKE_CURRENT_BINARY_DIR}
)

target_link_libraries(MbDFEMGui ${MbDFEMGui_LIBS})

if(MSVC)
    target_compile_options(MbDFEMGui PRIVATE /wd4251)
endif()

if(FREECAD_WARN_ERROR)
    target_compile_warn_error(MbDFEMGui)
endif()

SET_BIN_DIR(MbDFEMGui MbDFEMGui /Mod/MbDFEM)
SET_PYTHON_PREFIX_SUFFIX(MbDFEMGui)

install(TARGETS MbDFEMGui DESTINATION ${CMAKE_INSTALL_LIBDIR})
