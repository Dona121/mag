# Guía de diseño — Gobernación de Sucre

Sistema de diseño institucional para interfaces web. Basado en el
*Manual de Identidad de la Gobernación de Sucre (2025)* y consolidado a partir
de la implementación real del **Modelo de Alta Gerencia (MAG)**.

> Úsala como punto de partida para futuros proyectos: copia los tokens, respeta
> la jerarquía de color y la tipografía, y reaprovecha los patrones de
> componentes. El objetivo es que todas las herramientas de la Gobernación se
> vean como una sola familia.

---

## 1. Principios

1. **Sobriedad institucional.** El verde corporativo es la marca, pero en
   superficies grandes se usa la versión profunda (más oscura y seria); el verde
   brillante queda como **acento**, no como fondo dominante.
2. **Una sola tipografía: Montserrat.** Todo el peso visual se logra con
   variaciones de grosor, no mezclando fuentes.
3. **El color comunica estado**, no solo decora: verde = bien, ámbar/naranja =
   alerta, rojo = crítico, azul = dato neutro/secundario.
4. **Aire y orden.** Tarjetas con bordes suaves, sombras sutiles y mucho espacio
   en blanco antes que líneas duras.

---

## 2. Paleta de color

### Verdes corporativos (marca)
| Token | HEX | Uso |
|---|---|---|
| `--verde-primario` | `#109d39` | Acento principal: botones primarios, barras de progreso, indicadores positivos, líneas de acento. |
| `--verde-claro` | `#e3f4ea` | Fondos suaves, *hover* de filas, badges positivos. |
| `--verde-superficie` | `#0e4d2a` | Superficies grandes y sobrias: sidebar, encabezados de tabla, masthead. |
| `--verde-superficie-2` | `#08321b` | Degradados / capas más profundas del sidebar. |
| `--verde-superficie-3` | `#052013` | Base más oscura del degradado. |

### Colores funcionales
| Token | HEX | Significado |
|---|---|---|
| `--azul` | `#0b72ab` | Dato secundario / neutro, botón secundario, segunda serie en gráficos. |
| `--rojo` | `#d92a34` | Crítico, error, variación negativa, botón peligro. |
| `--naranja` | `#ffa700` | Alerta / destacado, notificaciones. |
| `--ambar` | `#d88c16` | Estado intermedio (semáforo "en proceso"), advertencias de texto. |

### Neutros
| Token | HEX | Uso |
|---|---|---|
| `--negro` | `#000000` | Texto sobre fondos muy claros / naranja. |
| `--gris-oscuro` | `#5a595d` | Texto principal. |
| `--gris-medio` | `#686868` | Texto secundario, etiquetas, *leads*. |
| `--gris-claro` | `#dfe0e1` | Bordes, separadores, fondos inactivos. |
| `--gris-fondo` | `#f5f6f7` | Fondo general de la aplicación. |
| `--blanco` | `#ffffff` | Tarjetas, superficies de contenido. |

### Semáforo de desempeño (convención del proyecto)
| Estado | Color | Umbral típico |
|---|---|---|
| Verde | `--verde-primario` | ≥ 80 % |
| Ámbar | `--ambar` / `--naranja` | ≥ 60 % |
| Rojo | `--rojo` | < 60 % |
| Cero / sin dato | `--gris-medio` | = 0 / N/A |

---

## 3. Tipografía

- **Familia única:** `Montserrat` (Google Fonts), con *fallback*
  `'Helvetica Neue', Arial, sans-serif`.
- **Pesos disponibles:** 300, 400, 500, 600, 700, 800, 900.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
```

### Escala y jerarquía
| Rol | Tamaño | Peso | Notas |
|---|---|---|---|
| Título de sección (`h1`) | 22 px | 800 | `letter-spacing: -.2px` |
| Valor KPI grande | 26–30 px | 800 | Línea apretada (1.1) |
| Título de tarjeta (`h2`) | 15 px | 700 | Acompañado de barra de acento verde |
| Texto base | 13–14 px | 400–500 | Color `--gris-oscuro` |
| Etiqueta / *lead* / metadato | 11–12.5 px | 600 | Mayúsculas + `letter-spacing` para *labels* |

> Regla práctica: la jerarquía se construye **bajando el tamaño y subiendo el
> peso**, no cambiando de color salvo para estado.

---

## 4. Tokens base (espaciado, formas, sombras)

```css
:root {
    --radio-base: 6px;                 /* radio estándar; tarjetas grandes 12px */
    --sombra-suave: 0 1px 2px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.05);
    --sombra-foco: 0 0 0 3px rgba(16,157,57,0.20);   /* foco verde accesible */
    --transicion: 220ms cubic-bezier(.4,.0,.2,1);

    /* Layout app interna */
    --sidebar-w: 240px;
    --sidebar-w-collapsed: 64px;
    --topbar-h: 52px;
}
```

- **Radios:** 6 px para botones/inputs/badges; 12 px para tarjetas KPI grandes.
- **Sombras:** siempre suaves; nunca sombras duras o de color.
- **Foco:** anillo verde translúcido (`--sombra-foco`) — no eliminar el *outline*
  sin reemplazo accesible.

---

## 5. Componentes (patrones reutilizables)

### Botones
| Clase | Estilo |
|---|---|
| `.btn-primario` | Fondo `--verde-primario`, texto blanco. Acción principal. |
| `.btn-secundario` | Fondo `--azul`, texto blanco. Acción alterna. |
| `.btn-naranja` | Fondo `--naranja`, texto negro. Destacado. |
| `.btn-peligro` | Fondo `--rojo`, texto blanco. Acciones destructivas. |
| `.btn-borde` | Fondo blanco, borde gris. Acción terciaria / "deshacer". |

Base: `inline-flex`, `gap: 8px`, `font-weight: 600`, `padding: 9px 18px`,
`border-radius: var(--radio-base)`, transición de `filter` en *hover*.

### Tarjetas
- `.card`: fondo blanco, borde `--gris-claro`, `--sombra-suave`, radio base.
  El `h2` lleva una barra de acento verde (`::before`, 4×18 px).
- `.stat-card` / `.kpi-card`: tarjeta de métrica con barra/borde lateral de
  color según estado (`.azul`, `.naranja`, `.rojo`, `.semaforo-pos/neg/cero`).

### Tablas
- `.table.std`: encabezado con fondo `--verde-superficie` y texto blanco en
  mayúsculas; filas con borde inferior `--gris-claro` y *hover* `--verde-claro`.
- Para mapas de calor en celdas, sombrear con el color de estado a opacidad
  variable: `rgba(16,157,57,α)` (verde) o `rgba(11,114,171,α)` (azul).

### Badges
| Clase | Uso |
|---|---|
| `.badge-activo` | Verde claro / texto verde superficie. |
| `.badge-inactivo` | Gris. |
| `.badge-azul` | Azul translúcido (`rgba(11,114,171,.12)`). |

### Mensajes / alertas
- Éxito: borde y fondo verde claro.
- Error: borde rojo, fondo `#fdecee`.
- Advertencia: borde naranja, fondo `#fff5e0`, texto `#a36a00`.

### Pestañas
- `.dash-tabs`: barra inferior gris; pestaña activa con borde inferior y texto
  `--verde-primario`.

---

## 6. Gráficos (Chart.js)

- **Vendorizar** Chart.js localmente (`static/vendor/chart.umd.min.js`); no
  depender de CDN en producción.
- Serie principal: `--verde-primario`. Serie secundaria/neutra: `--azul`.
  Positivo/negativo: verde/rojo.
- Líneas de meta/objetivo: línea **discontinua** en gris medio.
- Mantener ejes y leyendas en `--gris-medio`, tipografía Montserrat heredada.

---

## 7. Logos

Disponibles en `static/logos/` (versiones 2025):
- **Color completo:** `2025_logo-gob-Sucre_*.png` — sobre fondos claros.
- **Blanco:** `2025_Blanco_*` y `2025_solo-blanco_*` — sobre fondos verdes/oscuros
  (sidebar, masthead, pie).
- **Negro:** `2025_solo-negro_*` — usos monocromáticos sobre claro.

Reglas: respetar el área de protección, no deformar ni recolorear el logo, y
elegir la versión según el contraste del fondo (blanco sobre verde superficie).

---

## 8. Accesibilidad y buenas prácticas

- Contraste mínimo AA: texto principal en `--gris-oscuro` sobre `--blanco`/`--gris-fondo`.
- No comunicar estado **solo** con color: acompañar con texto o ícono.
- Conservar foco visible (`--sombra-foco`).
- Animaciones de entrada sutiles (IntersectionObserver + opacidad/translación);
  evitar movimiento excesivo.
- **Estáticos en producción:** con `DEBUG=False` ejecutar `collectstatic`
  (WhiteNoise). Optimizar el peso de las imágenes antes de subirlas.

---

## 9. Plantilla mínima de arranque (copiar y pegar)

```css
:root {
  /* Marca */
  --verde-primario:#109d39; --verde-claro:#e3f4ea;
  --verde-superficie:#0e4d2a; --verde-superficie-2:#08321b; --verde-superficie-3:#052013;
  /* Funcionales */
  --azul:#0b72ab; --rojo:#d92a34; --naranja:#ffa700; --ambar:#d88c16;
  /* Neutros */
  --negro:#000; --gris-oscuro:#5a595d; --gris-medio:#686868;
  --gris-claro:#dfe0e1; --gris-fondo:#f5f6f7; --blanco:#fff;
  /* Tokens */
  --radio-base:6px;
  --sombra-suave:0 1px 2px rgba(0,0,0,.06),0 2px 8px rgba(0,0,0,.05);
  --sombra-foco:0 0 0 3px rgba(16,157,57,.20);
  --transicion:220ms cubic-bezier(.4,0,.2,1);
}
* { box-sizing:border-box; }
body {
  margin:0; font-family:'Montserrat','Helvetica Neue',Arial,sans-serif;
  background:var(--gris-fondo); color:var(--gris-oscuro);
}
```

---

*Fuente: Manual de Identidad de la Gobernación de Sucre 2025 (Colorimetría
págs. 21–22, Tipografía pág. 26) + tokens implementados en MAG.*
