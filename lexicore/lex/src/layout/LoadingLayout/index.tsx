import {CircularProgress} from "@mui/material";
import React from "react";
import './LoadingLayout.css';
const LoadingLayout = () => {
    return <div className="loading-layout__container">
        <CircularProgress />
    </div>;
}

export default LoadingLayout;