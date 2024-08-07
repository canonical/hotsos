# From https://github.com/libvirt/libvirt-python used by Nova
PYTHON_LIBVIRT_EXCEPTIONS = [
    "libvirtError",
]

# Since there are many many exception types we need to cherry-pick the ones we
# care about to avoid search expresssions becoming too huge.
# e.g. sed -rn 's/^class\s+(\S+)\(.+/    "\1",/p' nova/exception.py
NOVA_EXCEPTIONS = [
    "ConvertedException",
    "NovaException",
    "EncryptionFailure",
    "VirtualInterfaceCreateException",
    "VirtualInterfaceMacAddressException",
    "VirtualInterfacePlugException",
    "VirtualInterfaceUnplugException",
    "GlanceConnectionFailed",
    "CinderConnectionFailed",
    "UnsupportedCinderAPIVersion",
    "CinderAPIVersionNotAvailable",
    "Forbidden",
    "ForbiddenWithAccelerators",
    "AdminRequired",
    "PolicyNotAuthorized",
    "ImageNotActive",
    "ImageNotAuthorized",
    "Invalid",
    "InvalidConfiguration",
    "InvalidBDM",
    "InvalidBDMSnapshot",
    "InvalidBDMVolume",
    "InvalidBDMImage",
    "InvalidBDMBootSequence",
    "InvalidBDMLocalsLimit",
    "InvalidBDMEphemeralSize",
    "InvalidBDMSwapSize",
    "InvalidBDMFormat",
    "InvalidBDMForLegacy",
    "InvalidBDMVolumeNotBootable",
    "TooManyDiskDevices",
    "InvalidBDMDiskBus",
    "InvalidAttribute",
    "ValidationError",
    "VolumeAttachFailed",
    "VolumeDetachFailed",
    "MultiattachNotSupportedByVirtDriver",
    "MultiattachNotSupportedOldMicroversion",
    "MultiattachToShelvedNotSupported",
    "MultiattachSwapVolumeNotSupported",
    "VolumeNotCreated",
    "ExtendVolumeNotSupported",
    "VolumeEncryptionNotSupported",
    "VolumeTaggedAttachNotSupported",
    "VolumeTaggedAttachToShelvedNotSupported",
    "NetworkInterfaceTaggedAttachNotSupported",
    "InvalidKeypair",
    "InvalidRequest",
    "InvalidInput",
    "InvalidVolume",
    "InvalidVolumeAccessMode",
    "StaleVolumeMount",
    "InvalidMetadata",
    "InvalidMetadataSize",
    "InvalidPortRange",
    "InvalidIpProtocol",
    "InvalidContentType",
    "InvalidAPIVersionString",
    "VersionNotFoundForAPIMethod",
    "InvalidGlobalAPIVersion",
    "ApiVersionsIntersect",
    "InvalidParameterValue",
    "InvalidAggregateAction",
    "InvalidAggregateActionAdd",
    "InvalidAggregateActionDelete",
    "InvalidAggregateActionUpdate",
    "InvalidAggregateActionUpdateMeta",
    "InvalidSortKey",
    "InvalidStrTime",
    "InvalidNUMANodesNumber",
    "InvalidName",
    "InstanceInvalidState",
    "InstanceNotRunning",
    "InstanceNotInRescueMode",
    "InstanceNotRescuable",
    "InstanceNotReady",
    "InstanceSuspendFailure",
    "InstanceResumeFailure",
    "InstancePowerOnFailure",
    "InstancePowerOffFailure",
    "InstanceRebootFailure",
    "InstanceTerminationFailure",
    "InstanceDeployFailure",
    "MultiplePortsNotApplicable",
    "InvalidFixedIpAndMaxCountRequest",
    "ServiceUnavailable",
    "ServiceNotUnique",
    "ComputeResourcesUnavailable",
    "HypervisorUnavailable",
    "ComputeServiceUnavailable",
    "ComputeServiceInUse",
    "UnableToMigrateToSelf",
    "OperationNotSupportedForSEV",
    "OperationNotSupportedForVTPM",
    "OperationNotSupportedForVDPAInterface",
    "InvalidHypervisorType",
    "HypervisorTooOld",
    "DestinationHypervisorTooOld",
    "ServiceTooOld",
    "TooOldComputeService",
    "DestinationDiskExists",
    "InvalidDevicePath",
    "DevicePathInUse",
    "InvalidCPUInfo",
    "InvalidIpAddressError",
    "InvalidDiskFormat",
    "InvalidDiskInfo",
    "DiskInfoReadWriteFail",
    "ImageUnacceptable",
    "ImageBadRequest",
    "ImageImportImpossible",
    "ImageQuotaExceeded",
    "InstanceUnacceptable",
    "InvalidUUID",
    "InvalidID",
    "ConstraintNotMet",
    "NotFound",
    "VolumeAttachmentNotFound",
    "VolumeNotFound",
    "VolumeTypeNotFound",
    "UndefinedRootBDM",
    "BDMNotFound",
    "VolumeBDMNotFound",
    "VolumeBDMIsMultiAttach",
    "VolumeBDMPathNotFound",
    "DeviceDetachFailed",
    "DeviceNotFound",
    "SnapshotNotFound",
    "DiskNotFound",
    "VolumeDriverNotFound",
    "VolumeDriverNotSupported",
    "InvalidImageRef",
    "AutoDiskConfigDisabledByImage",
    "ImageNotFound",
    "ImageDeleteConflict",
    "PreserveEphemeralNotSupported",
    "InstanceMappingNotFound",
    "InvalidCidr",
    "NetworkNotFound",
    "PortNotFound",
    "NetworkNotFoundForBridge",
    "NetworkNotFoundForInstance",
    "NetworkAmbiguous",
    "UnableToAutoAllocateNetwork",
    "NetworkRequiresSubnet",
    "ExternalNetworkAttachForbidden",
    "NetworkMissingPhysicalNetwork",
    "VifDetailsMissingVhostuserSockPath",
    "VifDetailsMissingMacvtapParameters",
    "DatastoreNotFound",
    "PortInUse",
    "PortRequiresFixedIP",
    "PortNotUsable",
    "PortNotUsableDNS",
    "PortBindingFailed",
    "PortBindingDeletionFailed",
    "PortBindingActivationFailed",
    "PortUpdateFailed",
    "AttachSRIOVPortNotSupported",
    "FixedIpNotFoundForAddress",
    "FixedIpNotFoundForInstance",
    "FixedIpAlreadyInUse",
    "FixedIpAssociatedWithMultipleInstances",
    "FixedIpInvalidOnHost",
    "NoMoreFixedIps",
    "FloatingIpNotFound",
    "FloatingIpNotFoundForAddress",
    "FloatingIpMultipleFoundForAddress",
    "FloatingIpPoolNotFound",
    "NoMoreFloatingIps",
    "FloatingIpAssociated",
    "NoFloatingIpInterface",
    "FloatingIpAssociateFailed",
    "FloatingIpBadRequest",
    "KeypairNotFound",
    "ServiceNotFound",
    "ConfGroupForServiceTypeNotFound",
    "ServiceBinaryExists",
    "ServiceTopicExists",
    "HostNotFound",
    "ComputeHostNotFound",
    "HostBinaryNotFound",
    "InvalidQuotaValue",
    "InvalidQuotaMethodUsage",
    "QuotaNotFound",
    "QuotaExists",
    "QuotaResourceUnknown",
    "ProjectUserQuotaNotFound",
    "ProjectQuotaNotFound",
    "QuotaClassNotFound",
    "QuotaClassExists",
    "OverQuota",
    "SecurityGroupNotFound",
    "SecurityGroupNotFoundForProject",
    "SecurityGroupExists",
    "SecurityGroupCannotBeApplied",
    "NoUniqueMatch",
    "NoActiveMigrationForInstance",
    "MigrationNotFound",
    "MigrationNotFoundByStatus",
    "MigrationNotFoundForInstance",
    "InvalidMigrationState",
    "ConsoleLogOutputException",
    "ConsoleNotAvailable",
    "ConsoleTypeInvalid",
    "ConsoleTypeUnavailable",
    "ConsolePortRangeExhausted",
    "FlavorNotFound",
    "FlavorNotFoundByName",
    "FlavorAccessNotFound",
    "FlavorExtraSpecUpdateCreateFailed",
    "CellTimeout",
    "SchedulerHostFilterNotFound",
    "FlavorExtraSpecsNotFound",
    "ComputeHostMetricNotFound",
    "FileNotFound",
    "ClassNotFound",
    "InstanceTagNotFound",
    "KeyPairExists",
    "InstanceExists",
    "FlavorExists",
    "FlavorIdExists",
    "FlavorAccessExists",
    "InvalidSharedStorage",
    "InvalidLocalStorage",
    "StorageError",
    "MigrationError",
    "MigrationPreCheckError",
    "MigrationSchedulerRPCError",
    "MalformedRequestBody",
    "ConfigNotFound",
    "PasteAppNotFound",
    "CannotResizeToSameFlavor",
    "ResizeError",
    "CannotResizeDisk",
    "FlavorMemoryTooSmall",
    "FlavorDiskTooSmall",
    "FlavorDiskSmallerThanImage",
    "FlavorDiskSmallerThanMinDisk",
    "VolumeSmallerThanMinDisk",
    "BootFromVolumeRequiredForZeroDiskFlavor",
    "NoValidHost",
    "RequestFilterFailed",
    "InvalidRoutedNetworkConfiguration",
    "MaxRetriesExceeded",
    "QuotaError",
    "TooManyInstances",
    "FloatingIpLimitExceeded",
    "MetadataLimitExceeded",
    "OnsetFileLimitExceeded",
    "OnsetFilePathLimitExceeded",
    "OnsetFileContentLimitExceeded",
    "KeypairLimitExceeded",
    "SecurityGroupLimitExceeded",
    "PortLimitExceeded",
    "AggregateNotFound",
    "AggregateNameExists",
    "AggregateHostNotFound",
    "AggregateMetadataNotFound",
    "AggregateHostExists",
    "InstancePasswordSetFailed",
    "InstanceNotFound",
    "InstanceInfoCacheNotFound",
    "MarkerNotFound",
    "CouldNotFetchImage",
    "CouldNotUploadImage",
    "TaskAlreadyRunning",
    "TaskNotRunning",
    "InstanceIsLocked",
    "ConfigDriveInvalidValue",
    "ConfigDriveUnsupportedFormat",
    "ConfigDriveMountFailed",
    "ConfigDriveUnknownFormat",
    "ConfigDriveNotFound",
    "InterfaceAttachFailed",
    "InterfaceAttachFailedNoNetwork",
    "InterfaceAttachPciClaimFailed",
    "InterfaceAttachResourceAllocationFailed",
    "InterfaceDetachFailed",
    "InstanceUserDataMalformed",
    "InstanceUpdateConflict",
    "UnknownInstanceUpdateConflict",
    "UnexpectedTaskStateError",
    "UnexpectedDeletingTaskStateError",
    "InstanceActionNotFound",
    "InstanceActionEventNotFound",
    "InstanceEvacuateNotSupported",
    "DBNotAllowed",
    "UnsupportedVirtType",
    "UnsupportedHardware",
    "UnsupportedRescueBus",
    "UnsupportedRescueDevice",
    "UnsupportedRescueImage",
    "Base64Exception",
    "BuildAbortException",
    "RescheduledException",
    "ShadowTableExists",
    "InstanceFaultRollback",
    "OrphanedObjectError",
    "ObjectActionError",
    "InstanceGroupNotFound",
    "InstanceGroupIdExists",
    "InstanceGroupSaveException",
    "ResourceMonitorError",
    "PciDeviceWrongAddressFormat",
    "PciDeviceInvalidDeviceName",
    "PciDeviceNotFoundById",
    "PciDeviceNotFound",
    "PciDeviceInvalidStatus",
    "PciDeviceVFInvalidStatus",
    "PciDevicePFInvalidStatus",
    "PciDeviceInvalidOwner",
    "PciDeviceRequestFailed",
    "PciDevicePoolEmpty",
    "PciInvalidAlias",
    "PciRequestAliasNotDefined",
    "PciConfigInvalidWhitelist",
    "PciRequestFromVIFNotFound",
    "InternalError",
    "PciDeviceDetachFailed",
    "PciDeviceUnsupportedHypervisor",
    "KeyManagerError",
    "VolumesNotRemoved",
    "VolumeRebaseFailed",
    "InvalidVideoMode",
    "RngDeviceNotExist",
    "RequestedVRamTooHigh",
    "SecurityProxyNegotiationFailed",
    "RFBAuthHandshakeFailed",
    "RFBAuthNoAvailableScheme",
    "InvalidWatchdogAction",
    "LiveMigrationNotSubmitted",
    "SelectionObjectsWithOldRPCVersionNotSupported",
    "LiveMigrationURINotAvailable",
    "UnshelveException",
    "MismatchVolumeAZException",
    "UnshelveInstanceInvalidState",
    "ImageVCPULimitsRangeExceeded",
    "ImageVCPUTopologyRangeExceeded",
    "ImageVCPULimitsRangeImpossible",
    "InvalidArchitectureName",
    "ImageNUMATopologyIncomplete",
    "ImageNUMATopologyForbidden",
    "ImageNUMATopologyRebuildConflict",
    "ImagePCINUMAPolicyForbidden",
    "ImageNUMATopologyAsymmetric",
    "ImageNUMATopologyCPUOutOfRange",
    "ImageNUMATopologyCPUDuplicates",
    "ImageNUMATopologyCPUsUnassigned",
    "ImageNUMATopologyMemoryOutOfRange",
    "InvalidHostname",
    "NumaTopologyNotFound",
    "MigrationContextNotFound",
    "SocketPortRangeExhaustedException",
    "SocketPortInUseException",
    "ImageSerialPortNumberInvalid",
    "ImageSerialPortNumberExceedFlavorValue",
    "SerialPortNumberLimitExceeded",
    "InvalidImageConfigDrive",
    "InvalidHypervisorVirtType",
    "InvalidMachineType",
    "InvalidMachineTypeUpdate",
    "UnsupportedMachineType",
    "InvalidVirtualMachineMode",
    "InvalidToken",
    "TokenInUse",
    "InvalidConnectionInfo",
    "InstanceQuiesceNotSupported",
    "InstanceAgentNotEnabled",
    "QemuGuestAgentNotEnabled",
    "SetAdminPasswdNotSupported",
    "MemoryPageSizeInvalid",
    "MemoryPageSizeForbidden",
    "MemoryPageSizeNotSupported",
    "CPUPinningInvalid",
    "CPUUnpinningInvalid",
    "CPUPinningUnknown",
    "CPUUnpinningUnknown",
    "ImageCPUPinningForbidden",
    "ImageCPUThreadPolicyForbidden",
    "ImagePMUConflict",
    "UnsupportedPolicyException",
    "CellMappingNotFound",
    "NUMATopologyUnsupported",
    "MemoryPagesUnsupported",
    "InvalidImageFormat",
    "UnsupportedImageModel",
    "HostMappingNotFound",
    "HostMappingExists",
    "RealtimeConfigurationInvalid",
    "CPUThreadPolicyConfigurationInvalid",
    "RequestSpecNotFound",
    "UEFINotSupported",
    "SecureBootNotSupported",
    "TriggerCrashDumpNotSupported",
    "UnsupportedHostCPUControlPolicy",
    "LibguestfsCannotReadKernel",
    "RealtimeMaskNotFoundOrInvalid",
    "OsInfoNotFound",
    "BuildRequestNotFound",
    "AttachInterfaceNotSupported",
    "AttachInterfaceWithQoSPolicyNotSupported",
    "NetworksWithQoSPolicyNotSupported",
    "CreateWithPortResourceRequestOldVersion",
    "InvalidReservedMemoryPagesOption",
    "ResourceProviderInUse",
    "ResourceProviderRetrievalFailed",
    "ResourceProviderAggregateRetrievalFailed",
    "ResourceProviderTraitRetrievalFailed",
    "ResourceProviderCreationFailed",
    "ResourceProviderDeletionFailed",
    "ResourceProviderUpdateFailed",
    "ResourceProviderNotFound",
    "ResourceProviderSyncFailed",
    "PlacementAPIConnectFailure",
    "PlacementAPIConflict",
    "ResourceProviderUpdateConflict",
    "InvalidResourceClass",
    "InvalidInventory",
    "InventoryInUse",
    "UsagesRetrievalFailed",
    "NotSupportedWithOption",
    "Unauthorized",
    "NeutronAdminCredentialConfigurationInvalid",
    "InvalidEmulatorThreadsPolicy",
    "InvalidCPUAllocationPolicy",
    "InvalidCPUThreadAllocationPolicy",
    "BadRequirementEmulatorThreadsPolicy",
    "InvalidNetworkNUMAAffinity",
    "InvalidPCINUMAAffinity",
    "PowerVMAPIFailed",
    "TraitRetrievalFailed",
    "TraitCreationFailed",
    "CannotMigrateToSameHost",
    "VirtDriverNotReady",
    "InvalidPeerList",
    "InstanceDiskMappingFailed",
    "NewMgmtMappingNotFoundException",
    "NoDiskDiscoveryException",
    "UniqueDiskDiscoveryException",
    "DeviceDeletionException",
    "OptRequiredIfOtherOptValue",
    "AllocationCreateFailed",
    "AllocationUpdateFailed",
    "AllocationMoveFailed",
    "AllocationDeleteFailed",
    "TooManyComputesForHost",
    "CertificateValidationFailed",
    "InstanceRescueFailure",
    "InstanceUnRescueFailure",
    "IronicAPIVersionNotAvailable",
    "ZVMDriverException",
    "ZVMConnectorError",
    "NoResourceClass",
    "ResourceProviderAllocationRetrievalFailed",
    "ConsumerAllocationRetrievalFailed",
    "ReshapeFailed",
    "ReshapeNeeded",
    "FlavorImageConflict",
    "MissingDomainCapabilityFeatureException",
    "HealPortAllocationException",
    "MoreThanOneResourceProviderToHealFrom",
    "NoResourceProviderToHealFrom",
    "UnableToQueryPorts",
    "UnableToUpdatePorts",
    "UnableToRollbackPortUpdates",
    "AssignedResourceNotFound",
    "PMEMNamespaceConfigInvalid",
    "GetPMEMNamespacesFailed",
    "VPMEMCleanupFailed",
    "RequestGroupSuffixConflict",
    "AmbiguousResourceProviderForPCIRequest",
    "UnexpectedResourceProviderNameForPCIRequest",
    "DeviceProfileError",
    "AcceleratorRequestOpFailed",
    "AcceleratorRequestBindingFailed",
    "InvalidLibvirtGPUConfig",
    "RequiredMixedInstancePolicy",
    "RequiredMixedOrRealtimeCPUMask",
    "MixedInstanceNotSupportByComputeService",
    "InvalidMixedInstanceDedicatedMask",
    "ProviderConfigException",
]

# sed -rn 's/^class\s+(\S+)\(.+/    "\1",/p' placement/exception.py
PLACEMENT_EXCEPTIONS = [
    "NotFound",
    "Exists",
    "InvalidInventory",
    "CannotDeleteParentResourceProvider",
    "ConcurrentUpdateDetected",
    "ResourceProviderConcurrentUpdateDetected",
    "ResourceProviderNotFound",
    "InvalidAllocationCapacityExceeded",
    "InvalidAllocationConstraintsViolated",
    "InvalidInventoryCapacity",
    "InvalidInventoryCapacityReservedCanBeTotal",
    "InventoryInUse",
    "InventoryWithResourceClassNotFound",
    "MaxDBRetriesExceeded",
    "ObjectActionError",
    "PolicyNotAuthorized",
    "ResourceClassCannotDeleteStandard",
    "ResourceClassCannotUpdateStandard",
    "ResourceClassExists",
    "ResourceClassInUse",
    "ResourceClassNotFound",
    "ResourceProviderInUse",
    "TraitCannotDeleteStandard",
    "TraitExists",
    "TraitInUse",
    "TraitNotFound",
    "ProjectNotFound",
    "ProjectExists",
    "UserNotFound",
    "UserExists",
    "ConsumerNotFound",
    "ConsumerExists",
    "ConsumerTypeNotFound",
    "ConsumerTypeExists",
]

# sed -rn 's/^class\s+(\S+)\(.+/    "\1",/p'  ./os_vif/exception.py
# sed -rn 's/^class\s+(\S+)\(.+/    "\1",/p'  ./vif_plug_ovs/exception.py
_OS_VIF_EXCEPTIONS = [
    "ExceptionBase",
    "LibraryNotInitialized",
    "NoMatchingPlugin",
    "NoMatchingPortProfileClass",
    "NoSupportedPortProfileVersion",
    "NoMatchingVIFClass",
    "NoSupportedVIFVersion",
    "PlugException",
    "UnplugException",
    "NetworkMissingPhysicalNetwork",
    "NetworkInterfaceNotFound",
    "NetworkInterfaceTypeNotDefined",
    "ExternalImport",
    "NotImplementedForOS",
    "AgentError",
    "MissingPortProfile",
    "WrongPortProfile",
    "RepresentorNotFound",
    "PciDeviceNotFoundById",
]
OS_VIF_EXCEPTIONS = [f"os_vif.exception.{exc}"
                     for exc in _OS_VIF_EXCEPTIONS]
