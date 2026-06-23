import subprocess
import time


def wifi_reconnect():
    """Reconnect network + randomize MAC address using the randmac alias."""
    interface = "enp0s3"

    try:
        print("[NETWORK] Randomizing MAC address and reconnecting...")
        result = subprocess.run("randmac", shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            print("[NETWORK] Reconnect + MAC randomization successful")
            time.sleep(4)
        else:
            print(f"[WARNING] randmac command failed: {result.stderr}")
            raise Exception("randmac failed")

    except Exception as e:
        print(f"[ERROR] Network reconnect failed: {e}")
        print("Falling back to manual reconnect...")

        try:
            subprocess.run(["sudo", "ip", "link", "set", interface, "down"], check=False)
            time.sleep(2)
            subprocess.run(["sudo", "ip", "link", "set", interface, "up"], check=False)
            time.sleep(3)
            print("[NETWORK] Simple reconnect completed")
        except Exception:
            print("[ERROR] Even fallback reconnect failed")
