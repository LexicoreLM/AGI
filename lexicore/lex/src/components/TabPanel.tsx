import React from "react";
import {Box} from "@mui/material";

interface TabPanelProps {
    children?: React.ReactNode;
    currTab: string;
    value: string;
}

function TabPanel(props: TabPanelProps) {
    const { children, value, currTab, ...other } = props;

    return (
        <div
            role="tabpanel"
            hidden={value !== currTab}
            id={`tabpanel-${currTab}`}
            aria-labelledby={`tab-${currTab}`}
            {...other}
        >
            {value === currTab && <div>{children}</div>}
        </div>
    )
}

export default TabPanel;