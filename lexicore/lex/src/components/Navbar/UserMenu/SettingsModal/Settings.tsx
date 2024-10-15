import './Settings.css';
import {Tab, Tabs} from "@mui/material";
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import React, {useCallback, useState} from "react";
import TabPanel from "../../../TabPanel";
import Person2Icon from '@mui/icons-material/Person2';
import ProfileSettings from "./ProfileSettings";
import StorageSettings from "./StorageSettings";
enum SettingsTabs {
    Profile = 'profile',
    Storage = 'storage',
}

interface SettingsProps {

}
const Settings = ({}: SettingsProps) => {
    const [currTab, setCurrTab] = useState<SettingsTabs>(SettingsTabs.Profile);

    const handleChange = useCallback((event: React.SyntheticEvent, newValue: SettingsTabs) => {
        setCurrTab(newValue);
    }, []);

    return (
        <section className="settings__container">
            <nav className="settings__nav">
                <Tabs
                    orientation="vertical"
                    variant="scrollable"
                    value={currTab}
                    onChange={handleChange}
                    sx={{ borderRight: 1, borderColor: 'divider' }}
                >
                    <Tab icon={<Person2Icon />} label="Profile" value={SettingsTabs.Profile} />
                    <Tab icon={<CloudUploadIcon />} label="Storage" value={SettingsTabs.Storage} />
                </Tabs>
            </nav>
            <TabPanel value={SettingsTabs.Profile} currTab={currTab}>
                <ProfileSettings />
            </TabPanel>
            <TabPanel value={SettingsTabs.Storage} currTab={currTab}>
                <StorageSettings />
            </TabPanel>
        </section>
    )
}

export default Settings;