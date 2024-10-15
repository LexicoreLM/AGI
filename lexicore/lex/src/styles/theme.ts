import {createTheme} from "@mui/material";

const darkTheme = createTheme({
    palette: {
        mode: 'dark',
        primary: {
            main: '#FFCC02',
            dark: '#FF8D03',
        },
        secondary: {
            main: '#BBBBBB',
            dark: '#1A1A1A',
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
    typography: {
        fontFamily: 'Play',
        h2: {
            fontSize: "24px",
            lineHeight: "30px",
        }
    },
    components: {
        MuiTab: {
            styleOverrides: {
                root: {
                    flexDirection: "row",
                    gap: "10px",
                    minHeight: "60px",
                }
            }
        },
        MuiInputBase: {
            styleOverrides: {
                root: {
                    backgroundColor: "rgba(255, 255, 255, .15)",
                }
            }
        },
        MuiOutlinedInput: {
            styleOverrides: {
                notchedOutline: {
                    border: "none",
                }
            }
        },
        MuiDialogActions: {
            styleOverrides: {
                root: {
                    padding: "20px",
                }
            }
        }
    }
});

export default darkTheme;