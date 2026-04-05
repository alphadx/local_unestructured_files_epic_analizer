---
name: documentador
description: "Documentador de desarrollo: al finalizar un cambio, agrega notas al README, mueve los TODO completados a DOCS/avances y actualiza TODO.md con nuevas tareas."
---

# Documentador

## Uso

Este skill guía al agente a actuar como un documentador del proyecto. Se aplica cuando realizas cambios en el código, corriges errores o agregas funcionalidades, y debes dejar documentación actualizada y ordenada.

## Qué hace

- Actualiza `README.md` con un resumen claro del cambio realizado.
- Si existe un `TODO.md` y se completó un elemento, elimina ese ítem y mueve el archivo generado (o la entrada de avance) a `DOCS/avances`.
- Si aparecen nuevas tareas o pendientes durante el desarrollo, las agrega o complementa en `TODO.md`.
- Verifica al final del desarrollo que:
  - `README.md` contiene la descripción del trabajo hecho
  - `TODO.md` refleja los nuevos pendientes
  - `DOCS/avances` contiene los avances documentados o TODO completados

## Criterios de calidad

- El `README.md` debe ser informativo y estar alineado con el cambio.
- No deben quedar referencias a tareas completadas en `TODO.md` si ya se movieron a `DOCS/avances`.
- Los nuevos TODOs deben ser claros, accionables y estar correctamente ubicados en `TODO.md`.

## Ejemplos de prompts

- "Documenta este cambio y actualiza los pendientes en TODO.md."
- "Agrega un resumen de la corrección a README y mueve el avance completado a DOCS/avances."
- "Soy documentador: actualiza el README y organiza los TODOs después de este desarrollo."
