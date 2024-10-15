import {IconButton} from "@mui/material";
import './MessengerHeader.css';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
const MessengerHeader = () => {
    return <div className="messenger__header">
        <IconButton>
            <RestartAltIcon/>
        </IconButton>
    </div>
}

export default MessengerHeader;