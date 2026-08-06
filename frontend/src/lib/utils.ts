/**
 * frontend/src/lib/utils.ts — Utilidades de UI y Formateadores (Capa 8 - Paso 4)
 * Ecosistema Automático de Licitaciones (bfr_incoop)
 */

import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Combina clases de Tailwind CSS sin duplicidad ni conflictos de especificidad.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Formatea un número como moneda en euros con formato español (ej. 150.000 €).
 */
export function formatCurrency(amount?: number | null): string {
  if (amount === undefined || amount === null || isNaN(amount)) {
    return '0 €';
  }
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Formatea un número como porcentaje (ej. 35,5 %).
 */
export function formatPercent(value?: number | null): string {
  if (value === undefined || value === null || isNaN(value)) {
    return '0%';
  }
  return `${value.toFixed(1)}%`;
}

/**
 * Formatea una fecha ISO 8601 a formato legible local (ej. 28 jul 2026, 14:30).
 */
export function formatDate(isoString?: string | null): string {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return isoString;
    return new Intl.DateTimeFormat('es-ES', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(date);
  } catch {
    return isoString;
  }
}

/**
 * Retorna la diferencia en días entre la fecha actual y una fecha límite ISO.
 */
export function getDaysRemaining(isoString?: string | null): number | null {
  if (!isoString) return null;
  try {
    const target = new Date(isoString).getTime();
    const now = new Date().getTime();
    const diffTime = target - now;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  } catch {
    return null;
  }
}
