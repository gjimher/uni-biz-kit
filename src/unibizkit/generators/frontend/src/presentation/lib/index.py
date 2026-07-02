def generate() -> str:
    """Barrel re-export so pages can `import { useSession, money } from '../lib'`."""
    return """// Shared helpers for custom presentation pages (presentation/*.jsx).
export * from './auth';
export * from './profile';
export * from './validations';
export * from './format';
export * from './workflow';
export * from './storage';
export * from './payment';
"""
