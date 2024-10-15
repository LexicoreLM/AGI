import PersonIcon from "@mui/icons-material/Person";
import {Menu, MenuItem} from "@mui/material";
import SettingsModal from "./SettingsModal";
import React, {useCallback, useState} from "react";
import {useAuth0} from "@auth0/auth0-react";

const UserMenu = () => {
    const {logout} = useAuth0();
    const [menuEl, setMenuEl] = useState<null | HTMLElement>(null);
    const [settingsModalOpened, setSettingsModalOpened] = useState<boolean>(false);

    const openMenu = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
        setMenuEl(event.currentTarget);
    }, []);

    const closeMenu = useCallback(() => {
        setMenuEl(null);
    }, []);

    const openSettingsModal = useCallback(() => {
        setSettingsModalOpened(true);
    }, []);

    const closeSettingsModal = useCallback(() => {
        setSettingsModalOpened(false);
    }, []);

    const handleLogout = useCallback(async () => {
        await logout();
    }, []);

    const handleOpenSettings = useCallback(async () => {
        closeMenu();
        openSettingsModal();
    }, [closeMenu, openSettingsModal]);

    return (<>
            <div id="navbar__settings-btn"
                 onClick={openMenu}
                 aria-controls={menuEl ? 'settings-menu' : undefined}
                 aria-haspopup="true"
                 aria-expanded={menuEl ? 'true' : undefined}>
                <PersonIcon/>
            </div>

            <Menu
                id="settings-menu"
                anchorEl={menuEl}
                open={!!menuEl}
                onClose={closeMenu}
                anchorOrigin={{
                    vertical: 'bottom',
                    horizontal: 'right',
                }}
                transformOrigin={{
                    vertical: 'top',
                    horizontal: 'right',
                }}
                MenuListProps={{
                    'aria-labelledby': 'navbar__settings-btn',
                }}
            >
                <MenuItem onClick={handleOpenSettings}>Settings</MenuItem>
                <MenuItem onClick={handleLogout}>Logout</MenuItem>
            </Menu>
            <SettingsModal opened={settingsModalOpened} handleClose={closeSettingsModal}/>
        </>
    )
}

export default UserMenu;