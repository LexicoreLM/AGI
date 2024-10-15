import React from 'react';
import './App.css';
import Navbar from "../Navbar";
import ChatWindow from "../ChatWindow";
import TasksView from "../TasksView";
import { useAuth0 } from '@auth0/auth0-react';

function App() {
  const { loginWithRedirect, logout, isAuthenticated, user } = useAuth0();

return !isAuthenticated ? (
      <div className="app">
        <button onClick={() => loginWithRedirect()}>Log In</button>
      </div>
      ) : (
      <div className="app">
        {/*<Navbar />*/ }
      <div className="app__content">
      <TasksView />
      <ChatWindow />
      </div>
      </div>
  )
}

export default App;
