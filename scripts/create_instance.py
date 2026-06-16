#!/usr/bin/env python3
"""
Script que intenta crear una instancia VM.Standard.A1.Flex (ARM, Always Free)
en Oracle Cloud. Pensado para correr repetidamente desde GitHub Actions hasta
que Oracle tenga capacidad disponible.

Si la instancia ya existe (porque una corrida anterior tuvo éxito), el script
no hace nada y termina con éxito.

Maneja tres tipos de fallo de forma distinta:
- Sin capacidad ("Out of host capacity"): esperado, termina con exit code 1
  para que el cron de GitHub Actions reintente en 10 minutos.
- Timeout de red transitorio: reintenta unas pocas veces dentro de la misma
  corrida (con espera corta) antes de rendirse con exit code 1.
- Cualquier otro error (credenciales, formato, etc.): error real, se imprime
  el detalle completo para depurar.
"""

import os
import sys
import time
import tempfile

import oci

# Cuántas veces reintentar dentro de esta misma corrida ante un timeout de red,
# y cuánto esperar entre intentos (en segundos).
NETWORK_RETRY_ATTEMPTS = 3
NETWORK_RETRY_WAIT_SECONDS = 15


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: falta la variable de entorno {name}")
        sys.exit(1)
    return value


def build_config() -> dict:
    """Construye el config de OCI a partir de variables de entorno (secrets)."""
    private_key_content = get_env("OCI_PRIVATE_KEY")

    # OCI SDK espera una ruta a archivo de clave, así que la escribimos a un
    # archivo temporal.
    key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    key_file.write(private_key_content)
    key_file.close()
    os.chmod(key_file.name, 0o600)

    config = {
        "user": get_env("OCI_USER_OCID"),
        "fingerprint": get_env("OCI_FINGERPRINT"),
        "tenancy": get_env("OCI_TENANCY_OCID"),
        "region": get_env("OCI_REGION"),
        "key_file": key_file.name,
    }
    oci.config.validate_config(config)
    return config


def instance_already_exists(compute_client, compartment_id: str, display_name: str) -> bool:
    """Revisa si ya existe una instancia con ese nombre (evita duplicados)."""
    response = compute_client.list_instances(compartment_id=compartment_id)
    for instance in response.data:
        if instance.display_name == display_name and instance.lifecycle_state not in (
            "TERMINATED",
            "TERMINATING",
        ):
            return True
    return False


def get_latest_ubuntu_arm_image(compute_client, compartment_id: str) -> str:
    """Busca la imagen Ubuntu 22.04 más reciente compatible con ARM (aarch64)."""
    images = compute_client.list_images(
        compartment_id=compartment_id,
        operating_system="Canonical Ubuntu",
        operating_system_version="22.04",
        shape="VM.Standard.A1.Flex",
        sort_by="TIMECREATED",
        sort_order="DESC",
    ).data

    if not images:
        print("ERROR: no se encontró ninguna imagen Ubuntu 22.04 ARM disponible.")
        sys.exit(1)

    return images[0].id


def is_out_of_capacity_error(e: "oci.exceptions.ServiceError") -> bool:
    message = str(getattr(e, "message", ""))
    code = str(getattr(e, "code", ""))
    return (
        "Out of capacity" in message
        or "Out of host capacity" in message
        or "OutOfCapacity" in code
    )


def print_service_error_details(e: "oci.exceptions.ServiceError") -> None:
    print(f"❌ Error inesperado de la API de Oracle: {e}")
    print("--- Detalle completo de la excepción ---")
    print(f"status: {e.status}")
    print(f"code: {e.code}")
    print(f"message: {e.message}")
    print(f"operation_name: {e.operation_name}")
    print(f"target_service: {e.target_service}")
    print(f"request_endpoint: {getattr(e, 'request_endpoint', 'N/A')}")


def run_attempt(config: dict) -> bool:
    """
    Ejecuta un intento completo: revisar si ya existe, buscar imagen, y lanzar
    la instancia. Devuelve True si terminó con éxito (instancia creada o ya
    existente), False si fue un "Out of host capacity" (caso esperado para
    reintentar más tarde vía cron).

    Cualquier otro error real (credenciales, formato, etc.) termina el proceso
    inmediatamente con sys.exit(1).
    """
    compartment_id = get_env("OCI_TENANCY_OCID")  # compartimento raíz
    subnet_id = get_env("OCI_SUBNET_OCID")
    availability_domain = get_env("OCI_AVAILABILITY_DOMAIN")
    display_name = os.environ.get("OCI_INSTANCE_NAME", "pasatedigital")

    ssh_public_key = get_env("OCI_SSH_PUBLIC_KEY").strip()
    # Por si la clave llegó con múltiples líneas o saltos de línea accidentales,
    # la colapsamos a una sola línea (un .pub válido siempre es una sola línea).
    ssh_public_key = " ".join(ssh_public_key.split())

    ocpus = float(os.environ.get("OCI_OCPUS", "4"))
    memory_gb = float(os.environ.get("OCI_MEMORY_GB", "24"))
    boot_volume_gb = int(os.environ.get("OCI_BOOT_VOLUME_GB", "50"))

    compute_client = oci.core.ComputeClient(config)

    if instance_already_exists(compute_client, compartment_id, display_name):
        print(f"La instancia '{display_name}' ya existe. No se hace nada más.")
        sys.exit(0)

    image_id = get_latest_ubuntu_arm_image(compute_client, compartment_id)
    print(f"Usando imagen: {image_id}")

    launch_details = oci.core.models.LaunchInstanceDetails(
        availability_domain=availability_domain,
        compartment_id=compartment_id,
        display_name=display_name,
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=ocpus,
            memory_in_gbs=memory_gb,
        ),
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=subnet_id,
            assign_public_ip=True,
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(
            image_id=image_id,
            boot_volume_size_in_gbs=boot_volume_gb,
        ),
        metadata={
            "ssh_authorized_keys": ssh_public_key,
        },
    )

    print("Intentando crear la instancia...")
    response = compute_client.launch_instance(launch_details)
    print("✅ ¡Instancia creada con éxito!")
    print(f"OCID: {response.data.id}")
    print(f"Estado: {response.data.lifecycle_state}")
    sys.exit(0)


def main():
    config = build_config()

    for attempt in range(1, NETWORK_RETRY_ATTEMPTS + 1):
        try:
            run_attempt(config)
            return  # run_attempt termina el proceso por sí mismo (sys.exit)

        except oci.exceptions.ServiceError as e:
            if is_out_of_capacity_error(e):
                print("⏳ Sin capacidad disponible todavía. Se reintentará en la próxima corrida.")
                sys.exit(1)  # falla "esperada", el workflow (cron) seguirá reintentando
            else:
                print_service_error_details(e)
                sys.exit(1)

        except (oci.exceptions.ConnectTimeout, oci.exceptions.RequestException) as e:
            print(
                f"⏳ Intento {attempt}/{NETWORK_RETRY_ATTEMPTS}: "
                f"problema de red transitorio al hablar con Oracle."
            )
            print(f"Detalle: {e}")
            if attempt < NETWORK_RETRY_ATTEMPTS:
                print(f"Esperando {NETWORK_RETRY_WAIT_SECONDS}s antes de reintentar...")
                time.sleep(NETWORK_RETRY_WAIT_SECONDS)
            else:
                print(
                    "Se agotaron los reintentos de red en esta corrida. "
                    "El cron volverá a intentar en 10 minutos."
                )
                sys.exit(1)

        except Exception as e:
            print(f"❌ Error no esperado: {type(e).__name__}: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
