# App de impresión para la tablet (reemplazo de RawBT)

La app **Impresora POS** convierte cualquier tablet Android del local en la
"jefa de la impresora": atiende la cola de tickets del POS y los manda a la
impresora térmica de red, **sin tocar nada por ticket** y **aunque la tablet
esté bloqueada** — las dos cosas que RawBT no podía.

Imprime todo lo que el POS encola: la comanda de cada orden, el ticket chico
de gaseosas, el resumen de cierre de caja y el ticket de prueba del Admin.

## Instalar (una sola vez)

1. En la tablet, abre el navegador y entra a la página de **Releases** del
   repositorio → release **"App de impresión para la tablet"** → descarga
   `pos-impresora.apk`.
2. Ábrelo. Android va a pedir **permitir instalar de orígenes desconocidos**
   para el navegador: acéptalo (es solo para este archivo).
3. Abre la app **Impresora POS** y llena:
   - **Dirección del POS**: la URL de siempre (la de Railway), o
     `http://IP-de-la-laptop:8000` si ese día corren en local.
   - **PIN del local**: el mismo de las otras pantallas.
4. Toca **▶ INICIAR**. Acepta la notificación si la pide.
5. Toca **🔋 Permitir correr con pantalla apagada** y acepta. Sin esto,
   algunos Android matan la app al rato de bloquear la tablet.

Listo. La app muestra en pantalla cada ticket que va saliendo ("✔ Ticket
#012 impreso") y una notificación fija dice que está trabajando.

## Cosas que hace sola

- **Tablet bloqueada**: sigue imprimiendo (servicio en primer plano +
  permiso de batería).
- **Se fue la luz / se apagó la tablet**: al prenderla, el servicio arranca
  solo si estaba iniciado.
- **Impresora apagada o sin papel**: el ticket **no se pierde** — queda en
  la cola del POS y se reintenta cada 3 segundos hasta que salga.
- **Internet parpadea**: reintenta sin duplicar tickets (recuerda cuáles ya
  imprimió aunque no haya podido avisarle al POS).

## Requisitos

- El POS en modo **puente** con la IP y puerto de la impresora puestos en
  **Admin → Configuración → Impresora de tickets** (la app los recibe de
  ahí; no se configuran en la tablet).
- La tablet y la impresora en la **misma red Wi-Fi** del local.
- Android 7 o más nuevo.

## Si algo no sale

La pantalla de la app dice qué pasa con sus propias palabras:

| Mensaje | Qué hacer |
|---|---|
| "El POS rechazó el PIN" | Corrige el PIN y vuelve a INICIAR |
| "Falta la IP de la impresora" | Ponla en Admin → Configuración |
| "No se pudo imprimir #…" | Impresora apagada, sin papel o con otra IP; el ticket espera en cola |
| "Sin conexión con el POS" | Revisa el Wi-Fi o la URL; reintenta solo |

## Cómo se compila (para el desarrollador)

GitHub Actions la compila solo: cada push a `main` que toque
`android-impresora/` publica el APK en el release `app-impresora`
(workflow `.github/workflows/app-impresora.yml`). El proyecto vive en
`android-impresora/` (Kotlin, sin dependencias externas: HttpURLConnection,
Socket y org.json de Android) y habla el mismo protocolo que
`scripts/puente_impresion.py`: `GET /api/print/cola` con `X-Pin-Local`,
bytes ESC/POS por TCP al puerto RAW, y confirmación por tipo de trabajo.
El APK va firmado con la llave debug: suficiente para instalarlo directo
en las tablets del local (no pasa por Play Store).
