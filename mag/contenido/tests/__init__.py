"""Suite de tests de la app `contenido` (MAG).

Ejecutar desde la carpeta `mag/`:
    python manage.py test --settings=mag.settings_test

Modulos:
  - test_parametrizacion : CRUD de catalogos y estructura (Modelo -> Pilar ->
    Indicador -> Subindicador -> Criterio).
  - test_evaluaciones    : crear evaluacion + diligenciar (CRUD de resultados,
    incluye la regresion del borrado de puntaje directo).
  - test_periodos        : toggles de estado/publicacion y edicion de umbral.
  - test_acceso          : login requerido, restricciones del rol Evaluador y
    acceso publico al reporte.
  - test_modelos_orm     : CRUD completo a nivel ORM (incluye Delete) y
    restricciones de integridad de los modelos.
"""
