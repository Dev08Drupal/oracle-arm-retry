# Reintento automático de instancia ARM en Oracle Cloud

Este repositorio reintenta crear una instancia `VM.Standard.A1.Flex` (4 OCPU, 24GB RAM, Always Free)
cada 10 minutos hasta que Oracle Cloud tenga capacidad disponible.

## Secrets necesarios (Settings → Secrets and variables → Actions)

| Secret | Descripción | Ejemplo |
|---|---|---|
| `OCI_USER_OCID` | OCID de tu usuario | `ocid1.user.oc1..xxxx` |
| `OCI_FINGERPRINT` | Fingerprint de tu clave de **API** (no la SSH) | `be:16:60:55:...` |
| `OCI_TENANCY_OCID` | OCID de tu tenancy (= compartimento raíz) | `ocid1.tenancy.oc1..xxxx` |
| `OCI_REGION` | Región | `sa-saopaulo-1` |
| `OCI_SUBNET_OCID` | OCID de la subred pública (no el de la VCN) | `ocid1.subnet.oc1.sa-saopaulo-1.xxxx` |
| `OCI_PRIVATE_KEY` | Contenido completo de la clave privada de **API** (incluye `BEGIN/END PRIVATE KEY`) | — |
| `OCI_AVAILABILITY_DOMAIN` | Nombre completo del AD. El prefijo de 4 letras es único por tenancy, cópialo desde tu propia consola | `wfha:SA-SAOPAULO-1-AD-1` |
| `OCI_SSH_PUBLIC_KEY` | Contenido de la clave pública **SSH** (la del formulario de Red al crear la instancia, no la de API) | `ssh-rsa AAAA...` |

⚠️ Hay dos pares de claves distintos en todo este proceso y es fácil confundirlos:
- **Clave de API** (`OCI_PRIVATE_KEY` / `OCI_FINGERPRINT`): autentica el script contra la API de Oracle. Se genera en *Configuración de usuario → Claves de API*.
- **Clave SSH** (`OCI_SSH_PUBLIC_KEY`): la que descargaste en el paso de "Red" al crear la instancia. Permite conectarte por SSH al servidor una vez creado. La privada de este par **no va en ningún secret**, se queda en tu PC.

## Cómo usarlo

1. Agrega los 8 secrets arriba.
2. El workflow corre solo cada 10 minutos automáticamente (`schedule`).
3. También puedes forzar una corrida manual: pestaña **Actions** → **Reintento Oracle ARM** → **Run workflow**.
4. Revisa los logs de cada corrida en la pestaña **Actions**:
   - `⏳ Sin capacidad disponible todavía` → normal, seguirá reintentando solo.
   - `✅ ¡Instancia creada con éxito!` → listo, ve a la consola de Oracle a verificarla.
5. Cuando la instancia se cree con éxito, **desactiva el workflow** (Actions → ⋯ → Disable workflow)
   para que deje de correr.

## Troubleshooting (errores reales que aparecieron al configurar esto)

**`CannotParseRequest` (status 400)**
El JSON enviado a Oracle estaba mal formado. La causa más común es el `OCI_AVAILABILITY_DOMAIN` con
el prefijo incorrecto. Verifícalo manualmente: ve a crear una instancia desde la consola web (sin
llegar a confirmarla) y copia el valor exacto que aparece bajo "Dominio de disponibilidad" — el
prefijo de 4 letras antes de `:SA-...` es único por cuenta, no es el mismo para todos.

**`Out of host capacity` (status 500, `code: InternalError`)**
Este es el caso "normal" y esperado que el script está diseñado para reintentar. Oracle cambió el
formato de este error con el tiempo — antes venía como `OutOfCapacity` (400), ahora puede venir
como `InternalError` (500) con el mensaje `"Out of host capacity."`. El script ya detecta ambos
formatos y termina con `exit code 1` controlado para que el workflow vuelva a intentar en 10 minutos,
sin marcarlo como fallo real.

**Confundir la clave SSH con la clave de API**
Ambas son archivos `.pem`/`.pub` con apariencia similar, pero cumplen funciones distintas (ver
sección de secrets arriba). Si `OCI_SSH_PUBLIC_KEY` tiene el contenido equivocado, normalmente no
genera un error de la API — la instancia se crearía igual, pero luego no podrías conectarte por SSH.

## Importante

- GitHub Actions en repos privados tiene minutos gratis limitados al mes, pero este job es muy
  rápido (segundos por corrida), así que no debería ser un problema en el plan gratuito.
- Una vez tengas tu instancia, **rota (regenera) tu clave de API** en Oracle Cloud por seguridad,
  sobre todo si alguno de estos valores quedó expuesto fuera de los secrets de GitHub.
