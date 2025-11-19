# 📘 Documentation Technique : Code Annoté & Expliqué

Ce document présente le code source des composants critiques avec une explication détaillée pour chaque bloc. C'est le guide ultime pour comprendre la mécanique interne.

---

# 1. `MCP_Client.py` : Le Gestionnaire de Connexions

Ce fichier gère les connexions asynchrones aux serveurs MCP.

### 🔒 Gestion de la Concurrence et État

```python
class UniversalMCPClient:
    def __init__(self):
        self._servers: Dict[str, ServerInfo] = {}
        self._lock = asyncio.Lock()
        self._closed = False
```
**Explication :**
*   `self._servers` : Notre "registre" en mémoire. Il stocke les objets `ServerInfo` (qui contiennent la session active) pour chaque serveur connecté.
*   `self._lock = asyncio.Lock()` : **Crucial**. C'est un "Mutex" (Mutual Exclusion).
    *   **Pourquoi ?** Dans un environnement asynchrone, plusieurs tâches peuvent s'exécuter "en même temps" (entrelacées). Si une tâche essaie de lire `_servers` pendant qu'une autre le modifie (ex: suppression d'un serveur), cela peut créer des bugs aléatoires ou des crashs.
    *   Le verrou garantit qu'une seule tâche touche à `_servers` à la fois.

### 🔌 La Connexion (Le Cœur du Réacteur)

```python
async def _connect_server(self, config: ServerConfig) -> ServerInfo:
    stack = AsyncExitStack()
    
    try:
        # ... (choix du transport) ...
        if config.transport == "stdio":
            session = await self._connect_stdio(config, stack)
        
        await session.initialize()
        tools_response = await session.list_tools()
        
        return ServerInfo(..., stack=stack)
```
**Explication :**
*   `stack = AsyncExitStack()` : C'est l'outil magique de Python pour gérer les ressources.
    *   Une connexion MCP, c'est plusieurs couches : Processus -> Flux Entrée -> Flux Sortie -> Session.
    *   Chaque couche doit être fermée proprement.
    *   `AsyncExitStack` empile ces contextes. Si on quitte la fonction sans erreur, la pile reste "vivante" (les connexions restent ouvertes). On stocke cette `stack` dans `ServerInfo` pour pouvoir la fermer plus tard (`stack.aclose()`).
*   `await session.initialize()` : Le "Handshake". On dit "Bonjour" au serveur MCP pour vérifier qu'il parle la même langue (protocole) que nous.
*   `await session.list_tools()` : On récupère **tout de suite** la liste des outils. On ne veut pas faire un appel réseau à chaque fois qu'on a besoin de savoir si un outil existe.

### 🛠️ Appel d'Outil Sécurisé

```python
async def call_tool(self, server_name, tool_name, arguments, timeout=None):
    async with self._lock:
        server_info = self._servers.get(server_name)
        # ... vérifications ...

    if timeout:
        result = await asyncio.wait_for(
            server_info.session.call_tool(tool_name, arguments or {}),
            timeout=timeout
        )
    else:
        result = await server_info.session.call_tool(...)
```
**Explication :**
*   `async with self._lock` : On protège la lecture. On s'assure que le serveur ne va pas disparaître (être supprimé) pendant qu'on récupère ses infos.
*   `asyncio.wait_for(..., timeout=timeout)` : **Sécurité**.
    *   Si un outil (ex: un script Python mal codé) boucle à l'infini, on ne veut pas bloquer notre serveur principal.
    *   Si le délai est dépassé, Python tue la tâche et lève une erreur `TimeoutError`, ce qui nous permet de reprendre la main.

---

# 2. `ChatManager.py` : L'Intelligence Agentique

Ce fichier gère la conversation et la boucle de décision (ReAct).

### 🔄 La Boucle Principale (The Agent Loop)

```python
async def _process_conversation_loop(self) -> str:
    iteration = 0
    while iteration < self.max_iterations:
        iteration += 1
        
        # 1. Appel à l'IA
        response_message = await self._call_llm()
        
        # 2. Ajout de la réponse à l'historique
        self.conversation_history.append(assistant_message)
        
        # 3. Vérification : L'IA veut-elle utiliser des outils ?
        if assistant_message.tool_calls:
            # Exécution des outils
            tool_results = await self._execute_tool_calls(assistant_message.tool_calls)
            
            # Ajout des résultats à l'historique
            for result in tool_results:
                self.conversation_history.append(tool_message)
            
            # 4. REBOUCLAGE
            continue
            
        # Sinon, on a fini
        return assistant_message.content
```
**Explication :**
*   `while iteration < self.max_iterations` : On empêche l'IA de tourner en rond indéfiniment (sécurité).
*   `if assistant_message.tool_calls` : C'est ici que l'IA devient "active". Elle ne répond pas juste du texte, elle envoie une commande structurée (JSON) pour dire "Exécute l'outil X".
*   `continue` : **La ligne la plus importante**.
    *   Au lieu de s'arrêter et de répondre à l'utilisateur, on **repart au début de la boucle**.
    *   On rappelle l'LLM avec un historique enrichi : [Question User] -> [Pensée IA] -> [Résultat Outil].
    *   L'LLM peut alors analyser le résultat et formuler sa réponse finale.

### ⚡ Exécution Parallèle

```python
async def _execute_tool_calls(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
    # Création des tâches
    tasks = [
        tool_call.execute(self.mcp_client)
        for tool_call in tool_calls
    ]
    
    # Exécution simultanée
    results = await asyncio.gather(*tasks, return_exceptions=True)
```
**Explication :**
*   Si l'IA demande 3 outils (ex: "Météo Paris", "Météo Londres", "Météo Tokyo"), on ne les lance pas l'un après l'autre.
*   `asyncio.gather` les lance **tous en même temps**.
*   Si "Météo Paris" prend 2s, "Londres" 1s et "Tokyo" 3s, le tout prendra 3s (le plus long) au lieu de 6s (la somme). C'est un gain de performance énorme.

---

# 3. `app.py` : Le Serveur Web (FastAPI)

Ce fichier fait le lien entre le web et notre logique.

### 💉 Injection de Dépendance (La Session DB)

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```
**Explication :**
*   C'est un "Context Manager" sous forme de générateur.
*   `yield db` : Donne la connexion à la fonction qui en a besoin.
*   `finally: db.close()` : **Garantie absolue**. Quoi qu'il arrive (succès, erreur, crash dans la fonction), ce bloc sera exécuté. On est sûr à 100% de ne jamais laisser une connexion ouverte ("leak"), ce qui finirait par planter la base de données.

### 🧠 Reconstruction de l'État (Stateless Architecture)

```python
@app.post("/chat/{session_id}")
async def chat(session_id: str, request: ChatRequest, db: Session = Depends(get_db)):
    
    # 1. Récupération de la session
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    
    # 2. Reconstruction de l'historique
    history = []
    for msg in db_session.messages:
        history.append(Message(...))
    
    # 3. Résurrection du ChatManager
    chat_manager = ChatManager(mcp_client=mcp_client, history=history)
```
**Explication :**
*   Le serveur ne garde **rien** en mémoire vive (RAM) concernant la conversation.
*   À chaque fois que vous envoyez un message :
    1.  On va chercher tout l'historique dans le disque dur (SQLite).
    2.  On recrée un cerveau (`ChatManager`) tout neuf et on lui injecte ces souvenirs.
    3.  Il traite le message.
    4.  On sauvegarde les nouveaux souvenirs.
    5.  On détruit le cerveau.
*   **Avantage** : Si le serveur redémarre, on ne perd rien. Si on a 1 million d'utilisateurs, on ne sature pas la RAM.

### 💾 Sauvegarde Différentielle (Optimisation)

```python
    # Avant le traitement
    initial_history_count = len(history)
    
    # ... Traitement (l'IA réfléchit, appelle des outils, ajoute des messages) ...
    
    # Après le traitement
    new_messages = chat_manager.conversation_history[initial_history_count:]
    
    for msg in new_messages:
        db.add(MessageModel(...))
    
    db.commit()
```
**Explication :**
*   On ne sauvegarde pas tout l'historique à chaque fois (ce serait trop lent).
*   On regarde combien de messages on avait au début (`initial_history_count`).
*   On ne prend que les messages qui ont été ajoutés **après** cet index (`new_messages`).
*   `db.commit()` : On valide la transaction. C'est "tout ou rien". Soit tous les nouveaux messages sont sauvés, soit aucun (en cas d'erreur), pour ne pas corrompre la base.
