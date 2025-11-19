import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ChatInterface } from './components/ChatInterface';


function App() {
    return (
        <BrowserRouter>
            <Layout>
                <Routes>
                    <Route path="/" element={<ChatInterface />} />
                    <Route path="/chat/:sessionId" element={<ChatInterface />} />
                </Routes>
            </Layout>
        </BrowserRouter>
    );
}

export default App;
