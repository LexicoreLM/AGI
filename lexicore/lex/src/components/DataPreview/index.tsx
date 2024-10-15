import {IconButton, ToggleButton, ToggleButtonGroup} from '@mui/material';
import './TasksView.css';
import React, {useState} from "react";
import RawDataView from './RawDataView';
import RenderedDataView from "./RenderedDataView";
import CodeIcon from '@mui/icons-material/Code';
import PreviewIcon from '@mui/icons-material/Preview';
import RedoIcon from '@mui/icons-material/Redo';
import UndoIcon from '@mui/icons-material/Undo';
import Navbar from "../Navbar";
import ViewWrapper from "../ViewWrapper";

enum ViewType {
    Preview = 'preview',
    Raw = 'raw',
}

const markdown = `
| Month    | Savings |
| -------- | ------- |
| January  | $250    |
| February | $80     |
| March    | $420    |
`

const DataPreview = () => {
    const [currView, setCurrView] = useState<ViewType>(ViewType.Preview);

    const changeView = (event: React.MouseEvent<HTMLElement>, newAlignment: ViewType | null) => {
        if (newAlignment) {
            setCurrView(newAlignment);
        }
    };

    return (
        <ViewWrapper>
            <div className="data-view__header">
                <ToggleButtonGroup
                    value={currView}
                    exclusive
                    onChange={changeView}
                >
                    <ToggleButton value={ViewType.Preview}>
                        <PreviewIcon/>
                    </ToggleButton>
                    <ToggleButton value={ViewType.Raw}>
                        <CodeIcon/>
                    </ToggleButton>
                </ToggleButtonGroup>
                <div className="data-view__controls">
                    <IconButton><UndoIcon/></IconButton>
                    <IconButton disabled><RedoIcon/></IconButton>
                </div>
            </div>

            {currView === ViewType.Preview && <RenderedDataView data={markdown}/>}
            {currView === ViewType.Raw && <RawDataView data={markdown}/>}
        </ViewWrapper>
    );
}

export default DataPreview;