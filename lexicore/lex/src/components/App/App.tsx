import React, {useEffect} from 'react';
import './App.css';
import Navbar from "../Navbar";
import ChatWindow from "../ChatWindow";
import TasksView from "../TasksView";
import {useAuth0} from '@auth0/auth0-react';
import Login from "../../layout/Login";
import LexicoreLayout from "../../layout/LexicoreLayout";
import {Box, CircularProgress} from "@mui/material";
import LoadingLayout from "../../layout/LoadingLayout";

function App() {
    const {isAuthenticated, loginWithRedirect, isLoading, user} = useAuth0();

    useEffect(() => {
        if ((!isAuthenticated || !user) && !isLoading) {
            loginWithRedirect();
        }
    }, [isAuthenticated, user, isLoading]);

    if (!isAuthenticated || !user || isLoading) return (<LoadingLayout />);

    return <LexicoreLayout />
}

export default App;
