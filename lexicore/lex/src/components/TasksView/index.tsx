import {ToggleButton, ToggleButtonGroup} from '@mui/material';
import './TasksView.css';
import React, {useState} from "react";
import SpaceDashboardIcon from '@mui/icons-material/SpaceDashboard';
import ViewAgendaIcon from '@mui/icons-material/ViewAgenda';
import TagsView from './TagsView';
import CardsView from "./CardsView";
import {TaskData} from "../../interface/TaskData";
import Navbar from "../Navbar";

const tasks: TaskData[] = [
    {
        id: '1',
        title: 'Generate video',
        tags: ['video generation'],
        imageSrc: './icons/logos/youtube.svg'
    },
    {
        id: '12',
        title: 'Generate video',
        tags: ['video generation'],
        imageSrc: './icons/logos/ticktok.svg',
    },
    {
        id: '123',
        title: 'Write book',
        tags: ['text generation'],
        imageSrc: '',
    },
    {
        id: '1234',
        title: 'Test',
        tags: ['test tag'],
        imageSrc: '',
    }
]

enum ViewType {
    Tags = 'tags',
    Cards = 'cards',
}

const TasksView = () => {
    const [currView, setCurrView] = useState<ViewType>(ViewType.Tags);

    const changeView = (event: React.MouseEvent<HTMLElement>, newAlignment: ViewType | null) => {
        if (newAlignment) {
            setCurrView(newAlignment);
        }
    };

    return <section className="tasks-view__container">
        <Navbar />
        <div className="tasks-view__controls">
            <ToggleButtonGroup
                value={currView}
                exclusive
                onChange={changeView}
            >
                <ToggleButton value={ViewType.Tags}>
                    <ViewAgendaIcon/>
                </ToggleButton>
                <ToggleButton value={ViewType.Cards}>
                    <SpaceDashboardIcon/>
                </ToggleButton>
            </ToggleButtonGroup>
        </div>

        {currView === ViewType.Tags && <TagsView tasks={tasks}/>}
        {currView === ViewType.Cards && <CardsView tasks={tasks}/>}
    </section>
}

export default TasksView;