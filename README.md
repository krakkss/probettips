# proBetTips

MVP en Python para generar picks diarios de futbol y publicarlos en Telegram.

## Que hace ahora

- Lee partidos del dia desde `football-data.org` cuando hay token.
- Si no hay token, usa un conjunto de ejemplo para poder probar el flujo.
- Calcula una fuerza simple por equipo usando puesto, puntos por partido y diferencia de goles.
- Genera mercados conservadores tipo `1X`, `X2` y `Mas de 1.5 goles`.
- Selecciona 2 picks buscando una cuota combinada objetivo cercana a `1.60`.
- Formatea y envia el mensaje a Telegram.
- Guarda cada combinada diaria en historial local y luego la liquida cuando terminan los partidos.
- Calcula acumulado global de aciertos sobre total de pronosticos cerrados.

## Limites importantes

- No existe una forma seria de garantizar beneficio ni acierto del `99,9999%`.
- Flashscore es util como referencia visual, pero para automatizar conviene usar un proveedor de datos estable.
- Este MVP usa heuristicas. Para mejorar resultados hace falta backtesting, historico y recalibracion.

## Uso rapido

1. Crea un entorno virtual si quieres.
2. Copia `.env.example` a `.env` y rellena los valores.
3. Ejecuta:

```bash
python run.py preview --save
```

Para intentar publicar en Telegram:

```bash
python run.py send
```

Para liquidar los pronosticos finalizados y ver el acumulado:

```bash
python run.py settle
```

Si quieres mandar tambien el resultado a Telegram:

```bash
python run.py settle --notify
```

## Siguiente evolucion recomendada

- Sustituir la heuristica por un modelo entrenado con historico.
- Anadir un proveedor real de cuotas por casa de apuestas.
- Guardar resultados y medir yield, hit rate y CLV.
- Programar una ejecucion diaria.
