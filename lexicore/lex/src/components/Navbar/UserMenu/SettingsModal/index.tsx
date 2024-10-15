import {Button, Dialog, DialogActions, DialogContent, DialogTitle} from "@mui/material";
import React from "react";
import Settings from "./Settings";
import "./Settings.css";
interface SettingsModalProps {
    opened: boolean;
    handleClose: () => void;
}
const SettingsModal = ({opened, handleClose}: SettingsModalProps) => {
    return (
        <Dialog
            open={opened}
            onClose={handleClose}
            aria-labelledby="settings-modal-title"
            aria-describedby="settings-modal-description"
        >
            <DialogTitle id="settings-modal-title">
                Settings
            </DialogTitle>
            <DialogContent>
                <Settings />
            </DialogContent>
            <DialogActions>
                <Button color="secondary" variant="outlined" onClick={handleClose}>Close</Button>
                <Button onClick={handleClose} color="primary"  variant="contained">
                    Save
                </Button>
            </DialogActions>
        </Dialog>
    )
}

export default SettingsModal;