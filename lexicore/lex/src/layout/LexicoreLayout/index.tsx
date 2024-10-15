import TasksView from "../../components/TasksView";
import ChatWindow from "../../components/ChatWindow";
import React from "react";
import './LexicoreLayout.css';
import DataPreview from "../../components/DataPreview";
import Navbar from "../../components/Navbar";

const LexicoreLayout = () => {
    return <div className="lexicore-layout">
            {/*<TasksView/>*/}
            <DataPreview />
            <ChatWindow/>
    </div>
}

export default LexicoreLayout;