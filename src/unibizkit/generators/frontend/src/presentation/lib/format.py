from ....context import Context


def generate(ctx: Context) -> str:
    """Formatting helpers wired to the app's configured currency and locale."""
    currency = ctx.presentation_config["currency"]
    number_locale = ctx.presentation_config["number_locale"]

    return f"""// Formatting helpers using the app's configured currency and number locale.
export const CURRENCY = '{currency}';
export const NUMBER_LOCALE = '{number_locale}';

// Format a number as currency (e.g. 1234.5 -> "$1,234.50"). Null/undefined -> "—".
export function money(value) {{
  if (value == null || value === '') return '—';
  return new Intl.NumberFormat(NUMBER_LOCALE, {{ style: 'currency', currency: CURRENCY }}).format(Number(value));
}}

// Format a plain number with the configured locale.
export function number(value, options = {{}}) {{
  if (value == null || value === '') return '—';
  return new Intl.NumberFormat(NUMBER_LOCALE, options).format(Number(value));
}}

// Format a date/ISO string with the configured locale.
export function formatDate(value, options = {{ dateStyle: 'medium' }}) {{
  if (!value) return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(NUMBER_LOCALE, options).format(date);
}}
"""
