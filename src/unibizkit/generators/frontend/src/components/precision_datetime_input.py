def generate() -> str:
    return """import React from 'react';
import { DateTimeInput } from 'react-admin';

const formatDateTimeWithSeconds = value => {
  if (value == null || value === '') return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = number => String(number).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

export const PrecisionDateTimeInput = ({ precision = 'minute', inputProps, ...props }) => {
  const withSeconds = precision === 'second';
  return (
    <DateTimeInput
      {...props}
      format={withSeconds ? formatDateTimeWithSeconds : undefined}
      inputProps={withSeconds ? { ...inputProps, step: 1 } : inputProps}
    />
  );
};
"""
