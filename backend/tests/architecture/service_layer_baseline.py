from tests.architecture.service_layer_policy import ArchitectureViolation

EXPECTED_ENGINE_PURITY_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()
EXPECTED_SERVICE_RESULT_CONTRACT_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()
EXPECTED_SERVICE_CONSTRUCTOR_DEPENDENCY_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()
EXPECTED_TRANSPORT_LEAKAGE_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()
EXPECTED_CROSS_DOMAIN_BOUNDARY_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()
EXPECTED_SERVICE_MODULE_THRESHOLD_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()
EXPECTED_RUNTIME_WRAPPER_SERVICE_SURFACE_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()
