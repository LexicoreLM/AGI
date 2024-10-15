import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './components/App/App';
import reportWebVitals from './reportWebVitals';
import { ThemeProvider } from "@mui/material";
import darkTheme from "./styles/theme";
import { Auth0Provider } from '@auth0/auth0-react';

const root = ReactDOM.createRoot(
    document.getElementById('root') as HTMLElement
);
root.render(
    <React.StrictMode>
        <Auth0Provider
            domain="dev-hdfzflo5cshr35rs.us.auth0.com"
            clientId="emJsBipKnGRqa9HHKDfSA3UrPYa41qSp"
            authorizationParams={{
                redirect_uri: window.location.origin
            }}
        >
            <ThemeProvider theme={darkTheme}>
                <App />
            </ThemeProvider>
        </Auth0Provider>
    </React.StrictMode>
);

reportWebVitals();
