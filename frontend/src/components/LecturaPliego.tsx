/**
 * frontend/src/components/LecturaPliego.tsx — Los tres estados del análisis (Bloque 3 - Paso 5)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 *
 * El motor semántico funciona e integra el pipeline desde la Capa 5, y su trabajo quedaba
 * enterrado en la ficha de detalle. Tanto, que dirección llegó a creer que había que
 * ejecutarlo a mano con un `.py`.
 *
 * **Tres estados, y ni uno más** (contrato del Bloque 3, apartado F). La clasificación no se
 * hace aquí: llega resuelta de la API en `estado_lectura`, para que esté cubierta por
 * regresiones — el Cockpit no tiene suite y antes esta lógica vivía escrita dos veces, en la
 * tabla y en la ficha, fundiendo además «no se intentó» con «se intentó y salió mal».
 *
 * **Cada estado lleva palabra y nunca es un punto suelto**, que es la regla del sistema de
 * color: un punto significa categoría, un estado se nombra. Ver la cabecera de `index.css`.
 */

import React from 'react';
import { FileCheck2, FileQuestion, AlertTriangle } from 'lucide-react';
import { Badge } from './ui/Badge';
import type { BadgeVariant } from './ui/Badge';

export type EstadoLectura = 'LEIDO' | 'SIN_ANALIZAR' | 'DEGRADADO';

interface Presentacion {
  etiqueta: string;
  variante: BadgeVariant;
  icono: React.ReactNode;
  explicacion: string;
}

const PRESENTACION: Record<EstadoLectura, Presentacion> = {
  // Lo que hasta hoy no se decía nunca. El trabajo del Analista se notaba sólo porque NO
  // aparecía una advertencia, y una ausencia no es una afirmación: quien mira la fila no
  // tenía forma de saber si los riesgos venían del documento o de un rastreo del título.
  LEIDO: {
    etiqueta: 'Pliego leído',
    variante: 'success',
    icono: <FileCheck2 className="w-3 h-3" />,
    explicacion:
      'La IA ha leído el pliego. Los riesgos de esta fila salen del documento, no de una estimación.',
  },
  // Neutro, y es deliberado: **no es un fallo, es una ausencia**. Pintarlo de alarma diría
  // que el sistema se ha roto cuando lo que ocurre es que la fuente no trajo el pliego —sólo
  // la catalana lo hace de forma fiable— o que aún no le ha tocado el turno.
  SIN_ANALIZAR: {
    etiqueta: 'Sin analizar',
    variante: 'outline',
    icono: <FileQuestion className="w-3 h-3" />,
    explicacion:
      'No hay pliego o todavía no se ha procesado. Esta fila NO afirma que no haya riesgos: no se ha mirado.',
  },
  // Éste sí exige actuar, y por eso es el único de los tres que lleva color de atención:
  // hubo un intento, el dictamen no es fiable y conviene abrir el pliego a mano.
  DEGRADADO: {
    etiqueta: 'Lectura degradada',
    variante: 'warning',
    icono: <AlertTriangle className="w-3 h-3" />,
    explicacion:
      'Se intentó leer el pliego y el dictamen no es fiable. Los valores que muestra son por defecto, no hallazgos.',
  },
};

/** Normaliza cualquier valor recibido a uno de los tres estados. */
export const normalizarLectura = (estado?: string | null): EstadoLectura =>
  estado === 'LEIDO' || estado === 'DEGRADADO' ? estado : 'SIN_ANALIZAR';

export const etiquetaLectura = (estado: EstadoLectura): string =>
  PRESENTACION[estado].etiqueta;

export const explicacionLectura = (estado: EstadoLectura): string =>
  PRESENTACION[estado].explicacion;

/** `true` cuando lo que muestra la fila NO procede de haber leído el documento. */
export const sinLecturaFiable = (estado: EstadoLectura): boolean => estado !== 'LEIDO';

interface LecturaPliegoBadgeProps {
  estado: EstadoLectura;
  className?: string;
}

export const LecturaPliegoBadge: React.FC<LecturaPliegoBadgeProps> = ({
  estado,
  className,
}) => {
  const { etiqueta, variante, icono, explicacion } = PRESENTACION[estado];

  return (
    <Badge
      variant={variante}
      className={`text-[10px] gap-1 ${className ?? ''}`}
      title={explicacion}
    >
      {icono}
      {etiqueta}
    </Badge>
  );
};
