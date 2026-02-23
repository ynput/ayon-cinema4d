name = "cinema4d"
title = "Cinema4D"
version = "0.1.11"

# Name of client code directory imported in AYON launcher
# - do not specify if there is no client code
client_dir = "ayon_cinema4d"
app_host_name = "cinema4d"
project_can_override_addon_version = True

# Version compatibility with AYON server
# ayon_server_version = ">=1.0.7"
# Version compatibility with AYON launcher
# ayon_launcher_version = ">=1.0.2"

# Mapping of addon name to version requirements
# - addon with specified version range must exist to be able to use this addon
ayon_required_addons = {
    "core": ">0.4.4",
}
# Mapping of addon name to version requirements
# - if addon is used in same bundle the version range must be valid
ayon_compatible_addons = {
    # Needs Deadline support for Cinema4D render submissions
    "deadline": ">=0.5.19",
}
