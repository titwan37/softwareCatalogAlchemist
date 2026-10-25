import os

target_file = input(r"Enter the full file path to destroy: ").strip("\"'")

if os.path.exists(target_file):
    try:
        os.remove(target_file)
        print("Threat successfully destroyed.")
    except PermissionError:
        print("Permission denied. Ensure you have network write access.")
else:
    print("Target file not found.")