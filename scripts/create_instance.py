#!/usr/bin/env python3
"""
Script que intenta crear una instancia VM.Standard.A1.Flex (ARM, Always Free)
en Oracle Cloud. Pensado para correr repetidamente desde GitHub Actions hasta
que Oracle tenga capacidad disponible.

Si la instancia ya existe (porque una corrida anterior tuvo éxito), el script
no hace nada y termina con éxito.
"""

import os
import sys
import base64
import tempfile

import oci


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
    key_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".pem", delete=False
    )
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


def main():
    config = build_config()

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

    # --- Depuración: mostramos exactamente lo que vamos a enviar ---
    print("--- Valores usados para el launch ---")
    print(f"availability_domain: {availability_domain!r}")
    print(f"compartment_id: {compartment_id!r}")
    print(f"subnet_id: {subnet_id!r}")
    print(f"ocpus: {ocpus!r} ({type(ocpus)})")
    print(f"memory_gb: {memory_gb!r} ({type(memory_gb)})")
    print(f"boot_volume_gb: {boot_volume_gb!r} ({type(boot_volume_gb)})")
    print(f"ssh_public_key (primeros 40 chars): {ssh_public_key[:40]!r}")
    print(f"ssh_public_key (longitud): {len(ssh_public_key)}")
    print("--------------------------------------")

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

    try:
        print("Intentando crear la instancia...")
        response = compute_client.launch_instance(launch_details)
        print("✅ ¡Instancia creada con éxito!")
        print(f"OCID: {response.data.id}")
        print(f"Estado: {response.data.lifecycle_state}")
        sys.exit(0)

    except oci.exceptions.ServiceError as e:
        sin_capacidad = (
            "Out of capacity" in str(e.message)
            or "Out of host capacity" in str(e.message)
            or "OutOfCapacity" in str(e.code)
        )
        if sin_capacidad:
            print("⏳ Sin capacidad disponible todavía. Se reintentará en la próxima corrida.")
            sys.exit(1)  # falla "esperada", el workflow seguirá reintentando
        else:
            print(f"❌ Error inesperado de la API de Oracle: {e}")
            print(f"--- Detalle completo de la excepción ---")
            print(f"status: {e.status}")
            print(f"code: {e.code}")
            print(f"message: {e.message}")
            print(f"operation_name: {e.operation_name}")
            print(f"target_service: {e.target_service}")
            print(f"request_endpoint: {getattr(e, 'request_endpoint', 'N/A')}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error no esperado (no es ServiceError): {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
