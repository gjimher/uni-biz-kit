def generate(has_auth_provider: bool = False) -> str:
    if has_auth_provider:
        return """import * as React from 'react';
import { Layout } from 'react-admin';
import { MyMenu } from './MyMenu';
import { MyAppBar } from './MyAppBar';

export const MyLayout = (props) => <Layout {...props} menu={MyMenu} appBar={MyAppBar} />;
"""
    return """import * as React from 'react';
import { Layout } from 'react-admin';
import { MyMenu } from './MyMenu';

export const MyLayout = (props) => <Layout {...props} menu={MyMenu} />;
"""
