import {createTheme} from "@mui/material";

const darkTheme = createTheme({
    palette: {
        mode: 'dark',
        primary: {
            main: '#FFCC02',
            dark: '#FF8D03',
        },
        success: {
            main: '#346F44',
            dark: '#21462B'
        },
        error: {
            main: '#992E2E',
            dark: '#6F3434',
        }
    },
});

export default darkTheme;