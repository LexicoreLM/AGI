import React from 'react';
import './App.css';
import Navbar from "../Navbar";
import ChatWindow from "../ChatWindow";
import TasksView from "../TasksView";

function App() {
  return (
    <div className="app">
        {/*<Navbar />*/}
        <div className="app__content">
            <TasksView />
            <ChatWindow />
        </div>
    </div>
  );
}

export default App;
