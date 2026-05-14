def generate() -> str:
    return """import * as React from 'react';
import { SetPasswordPage, useSetPassword, useSupabaseAccessToken } from 'ra-supabase';
import { Form, required } from 'react-admin';
import { PasswordInput, SaveButton } from 'react-admin';

const MySetPasswordForm = () => {
    const access_token = useSupabaseAccessToken();
    const refresh_token = useSupabaseAccessToken({ parameterName: 'refresh_token' });

    const [, { mutateAsync: setPassword }] = useSetPassword({
        // Hard reload so the Supabase client re-initialises its session from
        // storage — a SPA navigation leaves the recovery token in memory and
        // PostgREST rejects subsequent API calls with that stale token.
        onSuccess: () => window.location.replace(import.meta.env.VITE_BASE_URI + '#/admin'),
    });

    const validate = (values) => {
        if (values.password !== values.confirmPassword) {
            return { password: 'Passwords do not match', confirmPassword: 'Passwords do not match' };
        }
    };

    const submit = (values) => setPassword({ access_token, refresh_token, password: values.password });

    return (
        <Form onSubmit={submit} validate={validate}>
            <PasswordInput source="password" label="Password" fullWidth validate={required()} autoComplete="new-password" />
            <PasswordInput source="confirmPassword" label="Confirm password" fullWidth validate={required()} />
            <SaveButton />
        </Form>
    );
};

export const MySetPasswordPage = () => (
    <SetPasswordPage>
        <MySetPasswordForm />
    </SetPasswordPage>
);
"""
