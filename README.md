# Reintento automático de instancia ARM en Oracle Cloud

Este repositorio reintenta crear una instancia `VM.Standard.A1.Flex` (4 OCPU, 24GB RAM, Always Free)
cada 10 minutos hasta que Oracle Cloud tenga capacidad disponible.

## Secrets necesarios (Settings → Secrets and variables → Actions)

| Secret | Descripción | Ejemplo |
|---|---|---|
| `OCI_USER_OCID` | OCID de tu usuario | `ocid1.user.oc1..xxxx` |
| `OCI_FINGERPRINT` | Fingerprint de tu clave API | `be:16:60:55:...` |
| `OCI_TENANCY_OCID` | OCID de tu tenancy (= compartimento raíz) | `ocid1.tenancy.oc1..xxxx` |
| `OCI_REGION` | Región | `sa-saopaulo-1` |
| `OCI_SUBNET_OCID` | OCID de la subred pública | `ocid1.subnet.oc1.sa-saopaulo-1.xxxx` |
| `OCI_PRIVATE_KEY` | Contenido completo del archivo `.pem` (incluye BEGIN/END) | — |
| `OCI_AVAILABILITY_DOMAIN` | Nombre completo del AD | `vMRs:SA-SAOPAULO-1-AD-1` |
| `OCI_SSH_PUBLIC_KEY` | Contenido de tu clave pública `.pub` | `ssh-rsa AAAA...` |

## Cómo usarlo

1. Agrega los 8 secrets arriba.
2. El workflow corre solo cada 10 minutos automáticamente (`schedule`).
3. También puedes forzar una corrida manual: pestaña **Actions** → **Reintento Oracle ARM** → **Run workflow**.
4. Revisa los logs de cada corrida en la pestaña **Actions** para ver si dice
   "Sin capacidad disponible" o "¡Instancia creada con éxito!".
5. Cuando la instancia se cree con éxito, **desactiva el workflow** (Actions → ⋯ → Disable workflow)
   para que deje de correr.

## Importante

- GitHub Actions en repos privados tiene minutos gratis limitados al mes, pero este job es muy
  rápido (segundos), así que no debería ser un problema en el plan gratuito.
- Una vez tengas tu instancia, **rota (regenera) tu clave de API** en Oracle Cloud por seguridad.