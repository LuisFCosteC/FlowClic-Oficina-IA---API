# FlowClic Oficina IA: análisis de los 19 hallazgos de seguridad

> Autor: Arquitecto · 2026-11-22 · Referencia normativa para DEV (S01–S13, C01–C05) y para QA (QS1–QS5, QC1).
> **Severidad:** rango cualitativo CVSS v3.1/v4 típico de la debilidad genérica. QA debe puntuar cada instancia real que encuentre con la calculadora CVSS (vector incluido en QA_REPORT).
> **Clasificación:** OWASP Top 10 2021 + CWE. Para el #18 se usa además el OWASP Top 10 para aplicaciones LLM (2025).
> La correspondencia con las tareas del proyecto está en la tabla final (§20).

---

## 1. Claves y secretos subidos a repositorios (GitHub)
1. **Clasificación estándar:** A05:2021-Security Misconfiguration · A07:2021-Identification and Authentication Failures · CWE-540 (Inclusion of Sensitive Information in Source Code), CWE-798 (Use of Hard-coded Credentials), CWE-312 (Cleartext Storage of Sensitive Information).
2. **Nivel de severidad:** **Crítica**.
3. **Vector de riesgo e impacto:** cualquiera con acceso al repositorio (o a un fork, una copia o el historial de git) obtiene credenciales válidas; hay bots que escanean GitHub en minutos. **C:** total (BD, APIs de IA). **I:** alta (escritura con esas credenciales). **D:** alta (borrado de la BD, consumo de cuota y costes).
4. **Causa raíz arquitectónica:** CI/CD y gestión de secretos (proceso de desarrollo).
5. **Estrategia de remediación defensiva:** secretos fuera del código (bóveda cifrada + `.env` ignorado por git); hook `pre-commit` de detección de secretos; *Secret scanning* y *Push protection* de GitHub; repos privados. Si se filtra uno: **rotar primero** y después purgar el historial (`git filter-repo`). Referencias: OWASP Secrets Management Cheat Sheet, NIST SP 800-57.

## 2. APIs, tokens y credenciales expuestos en el frontend/cliente
1. **Clasificación estándar:** A02:2021-Cryptographic Failures · A05:2021-Security Misconfiguration · CWE-200 (Exposure of Sensitive Information to an Unauthorized Actor), CWE-522 (Insufficiently Protected Credentials), CWE-798.
2. **Nivel de severidad:** **Alta–Crítica** (según el alcance de la credencial).
3. **Vector de riesgo e impacto:** todo lo que llega al navegador es público: bundle JS, variables `VITE_*`, `localStorage`, respuestas de red. Un atacante extrae la clave desde DevTools y llama directamente al proveedor (BD, LLM). **C:** alta. **I:** alta. **D:** media/alta (abuso de cuota y costes).
4. **Causa raíz arquitectónica:** Frontend y diseño de la arquitectura (falta un backend intermediario).
5. **Estrategia de remediación defensiva:** el cliente **nunca** recibe secretos; el backend actúa de intermediario. Solo `VITE_API_URL` en el front. Credenciales de solo escritura (la API nunca las devuelve, solo `••••last4`). Cookie de sesión `HttpOnly`. Prohibido guardar secretos en `localStorage` o en el estado global. Revisión de la pestaña Network en QA.

## 3. BD expuesta a internet o sin reglas de acceso por fila/colección (RLS/ACL)
1. **Clasificación estándar:** A01:2021-Broken Access Control · A05:2021-Security Misconfiguration · CWE-284 (Improper Access Control), CWE-668 (Exposure of Resource to Wrong Sphere), CWE-306 (Missing Authentication for Critical Function).
2. **Nivel de severidad:** **Crítica**.
3. **Vector de riesgo e impacto:** conexión directa a la BD (puerto o endpoint público, token en el cliente) o reglas permisivas que permiten leer o modificar todas las tablas sin pasar por la lógica de negocio. **C:** total. **I:** total. **D:** total.
4. **Causa raíz arquitectónica:** Base de datos y gestión de accesos (IAM).
5. **Estrategia de remediación defensiva:** el navegador nunca habla con la BD. Turso solo con token, preferiblemente de alcance limitado y con rotación. libSQL no tiene RLS, así que el **control de acceso se aplica en la API** con denegación por defecto y comprobación de rol en cada ruta. La API escucha en `127.0.0.1`; el archivo local no se sirve por HTTP; principio de mínimo privilegio en los tokens (lectura separada de escritura si el proveedor lo permite).

## 4. Acceso a registros ajenos cambiando identificadores en la URL (IDOR / BOLA)
1. **Clasificación estándar:** A01:2021-Broken Access Control · OWASP API Security 2023 API1 (BOLA) · CWE-639 (Authorization Bypass Through User-Controlled Key), CWE-862 (Missing Authorization).
2. **Nivel de severidad:** **Alta**.
3. **Vector de riesgo e impacto:** cambiar `/api/.../{id}` por el id de otro usuario o recurso permite leer, modificar o borrar datos ajenos (sesiones, perfiles, credenciales). **C:** alta. **I:** alta. **D:** media.
4. **Causa raíz arquitectónica:** Backend (autorización a nivel de objeto).
5. **Estrategia de remediación defensiva:** autorización **a nivel de objeto** en cada consulta (`WHERE id = ? AND user_id = <sesión>`); los recursos propios se resuelven desde la sesión (`/me/...`), nunca con un id de usuario en la URL; los UUID no son un control de seguridad; tests automáticos de acceso cruzado por cada ruta.

## 5. Endpoints de la API accesibles sin autenticación
1. **Clasificación estándar:** A07:2021-Identification and Authentication Failures · A01:2021-Broken Access Control · CWE-306 (Missing Authentication for Critical Function).
2. **Nivel de severidad:** **Crítica**.
3. **Vector de riesgo e impacto:** cualquiera que alcance la API ejecuta operaciones (crear o borrar agentes y tickets, aprobar, cambiar la conexión de BD). **C:** alta. **I:** alta. **D:** alta.
4. **Causa raíz arquitectónica:** Backend.
5. **Estrategia de remediación defensiva:** autenticación **global con denegación por defecto** (dependencia de FastAPI aplicada a la app) y lista blanca explícita (login, verificación MFA, health básico, setup protegido con código y localhost); test que recorre **todas** las rutas registradas y exige 401 sin sesión; SSE y Swagger "Try it out" también sujetos a sesión.

## 6. Pagos sin validación en el servidor (webhooks sin firma, montos manipulables)
1. **Clasificación estándar:** A04:2021-Insecure Design · A08:2021-Software and Data Integrity Failures · CWE-602 (Client-Side Enforcement of Server-Side Security), CWE-345 (Insufficient Verification of Data Authenticity), CWE-347 (Improper Verification of Cryptographic Signature).
2. **Nivel de severidad:** **Crítica** (cuando hay pagos).
3. **Vector de riesgo e impacto:** el cliente envía el importe o un webhook falsificado y obtiene bienes o servicios gratis o marca pedidos como pagados. **C:** baja. **I:** crítica (fraude financiero). **D:** baja.
4. **Causa raíz arquitectónica:** Backend y diseño de la integración.
5. **Estrategia de remediación defensiva:** importes calculados **solo en el servidor**; pasarela certificada PCI-DSS; verificación de la **firma HMAC** del webhook y de la marca de tiempo (anti-replay); idempotencia por `event_id`; conciliación con la API de la pasarela. **FlowClic Fase 1: no aplica (no hay pagos)**; queda como regla para el futuro.

## 7. Login sin límite de intentos ni protección contra fuerza bruta o credential stuffing
1. **Clasificación estándar:** A07:2021-Identification and Authentication Failures · CWE-307 (Improper Restriction of Excessive Authentication Attempts).
2. **Nivel de severidad:** **Alta**.
3. **Vector de riesgo e impacto:** prueba automatizada de contraseñas o de listas filtradas hasta acceder a una cuenta (incluida la de ADMIN). **C:** alta. **I:** alta. **D:** media (bloqueo masivo de cuentas).
4. **Causa raíz arquitectónica:** Backend y gestión de accesos (IAM).
5. **Estrategia de remediación defensiva:** limitación por IP (429 + `Retry-After`) y por cuenta con bloqueo progresivo; mensajes genéricos idénticos; comparación en tiempo constante y hash ficticio para usuarios inexistentes (contra la enumeración por tiempo); MFA obligatorio para los roles privilegiados; auditoría de los intentos fallidos. Referencias: OWASP Authentication Cheat Sheet, NIST SP 800-63B §5.2.2.

## 8. Formularios e inputs sin validación ni sanitización (SQLi, XSS…)
1. **Clasificación estándar:** A03:2021-Injection · CWE-89 (SQL Injection), CWE-79 (Cross-site Scripting), CWE-20 (Improper Input Validation).
2. **Nivel de severidad:** **Crítica** (SQLi) / **Alta** (XSS almacenado).
3. **Vector de riesgo e impacto:** SQLi: lectura o modificación arbitraria de la BD. XSS: ejecución de JS en el navegador de otro usuario (acciones en su nombre). **C:** alta. **I:** alta. **D:** media.
4. **Causa raíz arquitectónica:** Backend (consultas y validación) y Frontend (codificación de la salida).
5. **Estrategia de remediación defensiva:** **solo consultas parametrizadas** (prohibido interpolar SQL); validación estricta con Pydantic (`extra='forbid'`, longitudes y tipos); límite de tamaño del body; React escapa por defecto y queda prohibido `dangerouslySetInnerHTML`; cabeceras CSP, `nosniff` y `frame-ancestors`; pruebas con payloads de inyección en QA.

## 9. Dependencias de terceros obsoletas o con vulnerabilidades conocidas
1. **Clasificación estándar:** A06:2021-Vulnerable and Outdated Components · CWE-1104 (Use of Unmaintained Third Party Components), CWE-1395 (Dependency on Vulnerable Third-Party Component).
2. **Nivel de severidad:** **Alta** (la del CVE heredado: puede ser Crítica).
3. **Vector de riesgo e impacto:** explotación de CVE públicos en librerías (RCE, desbordamientos, *prototype pollution*), o una dependencia maliciosa (cadena de suministro). **C/I/D:** según el CVE, hasta total.
4. **Causa raíz arquitectónica:** CI/CD y gestión de la cadena de suministro.
5. **Estrategia de remediación defensiva:** lockfiles versionados y versiones exactas; `pip-audit` y `npm audit` en cada QA y antes de cada merge; Dependabot semanal; eliminar las dependencias sin uso; pocas dependencias (biblioteca estándar primero). Opcional: SBOM (CycloneDX).

## 10. Errores en producción que revelan stack traces, rutas internas o código
1. **Clasificación estándar:** A05:2021-Security Misconfiguration · CWE-209 (Generation of Error Message Containing Sensitive Information), CWE-497 (Exposure of Sensitive System Information).
2. **Nivel de severidad:** **Media**.
3. **Vector de riesgo e impacto:** reconocimiento: versiones, rutas, consultas y estructura interna que facilitan otros ataques. **C:** media. **I:** baja. **D:** baja.
4. **Causa raíz arquitectónica:** Backend (manejo de excepciones y configuración).
5. **Estrategia de remediación defensiva:** manejador global con formato único `{error:{code,message}}` y 500 genérico; `requestId` para correlacionar con los logs internos; modo depuración desactivado; sin cabeceras de versión; documentación (`/docs`) desactivada en producción; logs sin secretos.

## 11. Contraseñas en texto plano o sin hash moderno con sal
1. **Clasificación estándar:** A02:2021-Cryptographic Failures · CWE-256 (Plaintext Storage of a Password), CWE-916 (Use of Password Hash With Insufficient Computational Effort), CWE-759 (Use of a One-Way Hash without a Salt).
2. **Nivel de severidad:** **Crítica**.
3. **Vector de riesgo e impacto:** con una fuga de la BD, todas las contraseñas quedan expuestas al instante y se reutilizan en otros servicios. **C:** crítica. **I:** alta (suplantación). **D:** baja.
4. **Causa raíz arquitectónica:** Backend y base de datos.
5. **Estrategia de remediación defensiva:** **scrypt** (N=2^17, r=8, p=1) o Argon2id con **sal única** por usuario, parámetros guardados junto al hash para poder subirlos; comparación en tiempo constante; mínimo 12 caracteres. Referencia: OWASP Password Storage Cheat Sheet.

## 12. Sin backups automáticos ni plan de recuperación (DRP)
1. **Clasificación estándar:** sin correspondencia directa en el OWASP Top 10 (lo más cercano es A04:2021-Insecure Design); sin CWE específico (control operativo). Controles de referencia: ISO/IEC 27001:2022 A.8.13 (copias de seguridad), A.5.30 (continuidad TIC) y NIST CSF 2.0 PR.DS-11 / RC.RP.
2. **Nivel de severidad:** **Alta**.
3. **Vector de riesgo e impacto:** ransomware, borrado accidental o malicioso, o corrupción sin forma de recuperarse: pérdida permanente de datos. **C:** baja. **I:** alta. **D:** crítica.
4. **Causa raíz arquitectónica:** Operaciones e infraestructura.
5. **Estrategia de remediación defensiva:** backups automáticos programados con retención; regla 3-2-1; backups con los secretos **cifrados**; RPO y RTO definidos (24 h / 1 h); **pruebas de restauración periódicas**; DRP documentado; la clave maestra se guarda aparte (gestor de contraseñas), porque sin ella el backup no sirve.

## 13. Cuenta administradora genérica con una contraseña compartida
1. **Clasificación estándar:** A07:2021-Identification and Authentication Failures · CWE-1391 (Use of Weak Credentials), CWE-1392 (Use of Default Credentials), CWE-778 (Insufficient Logging: se pierde la trazabilidad individual).
2. **Nivel de severidad:** **Alta**.
3. **Vector de riesgo e impacto:** cualquier miembro (o ex-miembro) del equipo, o quien obtenga esa contraseña, tiene control total; imposible saber quién hizo qué; la rotación rara vez se hace. **C:** alta. **I:** alta. **D:** alta.
4. **Causa raíz arquitectónica:** Gestión de accesos (IAM).
5. **Estrategia de remediación defensiva:** **cuentas individuales** y nominativas; sin usuarios ni contraseñas por defecto (primer ADMIN creado por consola o asistente con código de un solo uso); RBAC con mínimo privilegio; auditoría por usuario; baja inmediata (desactivar = revocar sesiones); no se puede dejar el sistema sin ADMIN.

## 14. Sin autenticación multifactor (MFA/2FA) en los accesos privilegiados
1. **Clasificación estándar:** A07:2021-Identification and Authentication Failures · CWE-308 (Use of Single-factor Authentication).
2. **Nivel de severidad:** **Alta**.
3. **Vector de riesgo e impacto:** una contraseña robada (phishing, reutilización, *stuffing*) basta para tomar el control administrativo. **C:** alta. **I:** alta. **D:** alta.
4. **Causa raíz arquitectónica:** Gestión de accesos (IAM).
5. **Estrategia de remediación defensiva:** **TOTP obligatorio** (RFC 6238) para ADMIN, con el secreto cifrado en la BD; **reautenticación reciente** (≤10 min) para las acciones críticas (conexión de BD, usuarios, credenciales); códigos de un solo uso (anti-replay); evolución a WebAuthn/passkeys. Referencia: NIST SP 800-63B AAL2.

## 15. Credenciales, claves de API o cadenas de conexión hardcodeadas
1. **Clasificación estándar:** A07:2021-Identification and Authentication Failures · CWE-798 (Use of Hard-coded Credentials), CWE-259 (Use of Hard-coded Password).
2. **Nivel de severidad:** **Crítica**.
3. **Vector de riesgo e impacto:** quien lea el código, un binario o el bundle obtiene la credencial; no se puede rotar sin desplegar código. **C:** alta. **I:** alta. **D:** alta.
4. **Causa raíz arquitectónica:** Backend y código fuente (y CI/CD por no detectarlo).
5. **Estrategia de remediación defensiva:** toda credencial en la bóveda cifrada o, como mínimo, en variables de entorno; el `.env` solo con la clave maestra; detección automática de secretos (pre-commit y QA sobre el historial); rotación periódica; revisión de código.

## 16. Paneles administrativos accesibles por enlace directo sin sesión ni rol
1. **Clasificación estándar:** A01:2021-Broken Access Control · CWE-425 (Direct Request, "Forced Browsing"), CWE-862 (Missing Authorization), CWE-306.
2. **Nivel de severidad:** **Crítica**.
3. **Vector de riesgo e impacto:** conocer o adivinar la URL del panel da acceso a la configuración, los usuarios y los secretos. Ocultar el enlace en la UI no protege nada. **C:** alta. **I:** alta. **D:** alta.
4. **Causa raíz arquitectónica:** Backend (la autorización real) y Frontend (falsa sensación de seguridad).
5. **Estrategia de remediación defensiva:** **autorización en el servidor** en cada endpoint `/api/admin/*` (rol ADMIN + MFA, y MFA reciente para lo crítico); el front solo oculta la UI; tests 401/403 para VIEWER y OPERATOR; la documentación interactiva no da acceso sin sesión y se apaga en producción.

## 17. Sesiones y tokens que nunca caducan (sin expiración ni revocación)
1. **Clasificación estándar:** A07:2021-Identification and Authentication Failures · CWE-613 (Insufficient Session Expiration).
2. **Nivel de severidad:** **Media–Alta**.
3. **Vector de riesgo e impacto:** un token robado (XSS, equipo compartido, log) sirve para siempre; no se puede expulsar a un usuario dado de baja. **C:** alta. **I:** alta. **D:** baja.
4. **Causa raíz arquitectónica:** Backend y gestión de accesos (IAM).
5. **Estrategia de remediación defensiva:** token opaco aleatorio (32 B) guardado **como hash**; expiración por inactividad (30 min) y absoluta (8 h); logout, "cerrar todas las sesiones" y revocación automática al cambiar contraseña, rol o desactivar al usuario; cookie `HttpOnly; Secure; SameSite=Strict`. Referencia: OWASP Session Management Cheat Sheet.

## 18. IA (p. ej. Claude) con permisos totales y directos sobre la BD de producción
1. **Clasificación estándar:** OWASP Top 10 for LLM Applications 2025: **LLM01 Prompt Injection**, **LLM06 Excessive Agency**, **LLM02 Sensitive Information Disclosure** · A01:2021-Broken Access Control · CWE-250 (Execution with Unnecessary Privileges), CWE-269 (Improper Privilege Management), CWE-1427 (Improper Neutralization of Input Used for LLM Prompting).
2. **Nivel de severidad:** **Crítica**.
3. **Vector de riesgo e impacto:** un texto malicioso (en un ticket, un documento o una web leída por el agente) inyecta instrucciones y el modelo, con acceso total, extrae, modifica o borra datos, o filtra secretos hacia el exterior. **C:** crítica. **I:** crítica. **D:** alta.
4. **Causa raíz arquitectónica:** Gestión de accesos (IAM) y diseño de la arquitectura de integración de IA.
5. **Estrategia de remediación defensiva:** la IA **nunca recibe un cliente de BD**; actúa solo a través de los services con una **identidad de servicio de mínimo privilegio** (rol `AGENT`: tickets, eventos y memoria; nunca usuarios, ajustes, credenciales ni aprobaciones); las salidas del modelo se tratan como **entrada no confiable** (misma validación que HTTP); lista blanca de herramientas; **aprobación humana** para las acciones destructivas o sensibles; las claves de los modelos se descifran solo en memoria y nunca se pasan al modelo; entornos separados (nunca producción en las pruebas); auditoría de cada acción del agente.

## 19. Sin evaluaciones periódicas de seguridad (escaneo, modelado de amenazas, pentesting)
1. **Clasificación estándar:** A04:2021-Insecure Design (falta de modelado de amenazas) · A09:2021-Security Logging and Monitoring Failures (detección); sin CWE específico (control de proceso). Marcos: NIST SSDF SP 800-218, OWASP SAMM, OWASP ASVS 4.0.
2. **Nivel de severidad:** **Media** (agravante: deja sin detectar las debilidades de los puntos 1–18).
3. **Vector de riesgo e impacto:** las vulnerabilidades se acumulan sin detectarse hasta que un atacante las explota; el impacto es el del hallazgo no detectado. **C/I/D:** indirecto, potencialmente total.
4. **Causa raíz arquitectónica:** Gobierno de seguridad y CI/CD.
5. **Estrategia de remediación defensiva:** modelado de amenazas STRIDE al inicio de cada fase; auditoría de dependencias y detección de secretos en cada merge; checklist ASVS nivel 1–2 en QA (QS1–QS5) al cerrar cada fase; revisión de seguridad automática de commits; pentest ético antes de exponer la app fuera de localhost; cada hallazgo alto se convierte en tarea con responsable y fecha.

---

## 20. Correspondencia con FlowClic (estado a 2026-11-22)
| # | Medida (PLAN) | Tareas DEV | Verificación QA | Estado |
|---|---|---|---|---|
| 1 | §12.1, S11 | S11 | QS5 | Historial auditado: limpio. Hook pendiente |
| 2 | §12.1, §16.5 | F05, C05, F07 | QC1, QS3 | Pendiente |
| 3 | §12.3, §16 | S01, S09, C02 | QS3 | Bóveda (C02) en QA |
| 4 | §12.3 | S09 | QS3 | Pendiente |
| 5 | §12.4 | S09, C04 | QS1 | Pendiente (API solo en 127.0.0.1 mientras tanto) |
| 6 | — | — | — | No aplica (sin pagos) |
| 7 | §12.1 | S07 | QS2 | Pendiente |
| 8 | §12.1, §0.4 | S01, S09, T22 | QS3 | Validación Pydantic en curso (T22) |
| 9 | §12.1 | S11, F05 | QS5 | `pip-audit` sin vulnerabilidades (QP1) |
| 10 | §12.1 | T21, S01 | QS5 | Formato de errores (T21) en QA |
| 11 | §12.1 | S04 | QS1 | Pendiente |
| 12 | §12.1 | S12 | QS4 | Pendiente |
| 13 | §12.1, §16.3 | S05, C04, A07, S10 | QS3 | Pendiente |
| 14 | §12.1 | S08 | QS1 | Pendiente |
| 15 | §12.1, §16 | C01–C03, S11 | QC1, QS5 | C01 hecho; C02 y C03 en QA |
| 16 | §12.3, §13 | S09, F03 | QS3 | Pendiente |
| 17 | §12.1 | S06 | QS1 | Pendiente |
| 18 | §7, §12.1, §16.7 | S13 (diseño), Fase 2 | QS5 | Diseño documentado |
| 19 | §12.1 | S13 | QS5 | Este documento + revisión automática de commits activa |

**Regla para QA:** en QS1–QS5 y QC1, cada hallazgo se reporta en QA_REPORT con los **5 campos de este documento**, más: resultado (CUMPLE / NO CUMPLE / N/A), vector CVSS de la instancia encontrada y evidencia reproducible **sin pegar secretos**.
