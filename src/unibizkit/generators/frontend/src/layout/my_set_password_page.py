def generate() -> str:
    return """import * as React from 'react';
import { SetPasswordPage, useSetPassword } from 'ra-supabase';
import { Form, required, useNotify } from 'react-admin';
import { PasswordInput, SaveButton } from 'react-admin';
import { supabaseClient } from '../supabaseClient';

// Two ways to arrive here with a usable credential (see index.jsx):
// - Older supabase-js leaves the recovery tokens as query params of the
//   rewritten URL, and setPassword() consumes them.
// - Newer supabase-js (>= 2.107) consumes the recovery URL itself and already
//   holds the session, so no tokens remain and the password is updated on it.
const getHashQueryParam = (name) => {
    const queryIndex = window.location.hash.indexOf('?');
    if (queryIndex === -1) return null;
    return new URLSearchParams(window.location.hash.substring(queryIndex + 1)).get(name);
};

const MySetPasswordForm = () => {
    const notify = useNotify();
    const access_token = getHashQueryParam('access_token');
    const refresh_token = getHashQueryParam('refresh_token');

    // Hard reload so the Supabase client re-initialises its session from
    // storage — a SPA navigation leaves the recovery token in memory and
    // PostgREST rejects subsequent API calls with that stale token.
    const onSuccess = () => window.location.replace(import.meta.env.VITE_BASE_URI + '#/admin');
    const [, { mutateAsync: setPassword }] = useSetPassword({ onSuccess });

    // Without URL tokens only a live recovery session can change the password;
    // anyone landing here without either has nothing to work with.
    React.useEffect(() => {
        if (access_token && refresh_token) return;
        supabaseClient.auth.getSession().then(({ data: { session } }) => {
            if (!session) window.location.hash = '#/login';
        });
    }, [access_token, refresh_token]);

    const validate = (values) => {
        if (values.password !== values.confirmPassword) {
            return { password: 'Passwords do not match', confirmPassword: 'Passwords do not match' };
        }
    };

    const submit = async (values) => {
        if (access_token && refresh_token) {
            return setPassword({ access_token, refresh_token, password: values.password });
        }
        const { error } = await supabaseClient.auth.updateUser({ password: values.password });
        if (error) {
            notify(error.message, { type: 'error' });
            return;
        }
        onSuccess();
    };

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
