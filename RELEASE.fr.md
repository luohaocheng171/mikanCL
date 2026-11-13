# MikanCL v5.2.0 — Notes de version

[中文](RELEASE.md) · [English](RELEASE.en.md) · [Русский](RELEASE.ru.md) · **Français** · [日本語](RELEASE.ja.md)

Date de publication : 2026-11-13

## Nouveautés de la v5.2.0

- **Page « Paramètres de version » autonome dans la version embellie** : reprise complète des 7 onglets de la version classique (Aperçu, Paramètres de jeu, Mods, Packs de ressources, Packs de shaders, Modpacks, Gestion des versions), y compris l'export de script de lancement, le bilan de santé et la réparation par lot, l'export de configuration par lot, les sauvegardes, ainsi que les outils graine de monde / captures / rapports de crash / graphe de mods / dépendances ; les instances et versions se changent en haut
- **Conversion de format de sauvegarde et import d'anciens mondes** : conversion multithread de 2009 Classic / Indev / Alpha / McRegion → Anvil → version cible, avec remappage des ID de blocs et sauvegarde automatique ; les anciens noms (`server_level.dat`, `*.mine`, un `level.dat` unique dans une archive Classic) sont détectés, convertis et importés en un clic
- **Choix du paquet Java** : le centre Java prend en charge les installateurs ZIP / MSI / EXE ; la variante ZIP est extraite automatiquement et son dossier `bin` est ajouté au PATH
- **Guidage des états vides** : sans version sur l'accueil, sans recherche dans le centre de contenu ou sans tâche dans le centre de téléchargement, un bouton « Que faire ensuite » propose un mini-tutoriel et un accès direct au téléchargement d'une version ou à l'installation d'un modpack, au lieu d'un simple « Rien »
- **Effet de verre réglable** : Paramètres → Apparence ajoute des réglages de luminosité du verre, d'arrondi, de taille des boutons et de couleur du texte, avec réinitialisation en un clic
- **Glisser-déposer global** : déposez un mod ou un dossier de mods pour choisir la version de destination ; pour un modpack, choisissez « ajouter à une version existante » ou « télécharger d'abord une version vanilla »
- **Vues « Courant / Avancé » des paramètres** : seuls les paramètres courants sont affichés par défaut, avec un bouton « Tout afficher »
- **Filet de sécurité** : « Revenir à la dernière configuration démarrable » et export de la configuration JVM / modpack actuelle en extrait `.mikan` partageable
- **Navigation facilitée** : entrée « Récemment utilisé », suggestions de fonctions associées en bas des pages et palette de commandes `Ctrl+K`
- **Résumé de lancement plus clair** : après le lancement, le launcher explique les paramètres appliqués automatiquement (G1GC, mémoire, options GC ignorées) au lieu de les cacher dans le journal
- **Outils de métadonnées de sauvegarde** : éditeur pour le nom du monde, le mode de jeu, la difficulté, la météo, l'heure, le point d'apparition et les règles courantes, ainsi que le réétiquetage du `level.dat` vers une version cible (la conversion complète de format est décrite dans « Conversion de format de sauvegarde et import d'anciens mondes » ci-dessus) ; `level.dat` est sauvegardé automatiquement avant écriture (5 dernières copies conservées)
- **Test d'adresse multijoueur** : l'adresse générée par Terracotta est testée automatiquement (disponibilité et latence), avec une relance manuelle, dans les deux éditions
- **Dossiers au choix** : les dossiers de sauvegarde, de téléchargement, d'importation de mondes et d'installation de modpacks sont choisis par l'utilisateur, plus de chemins imposés

## Correctifs et ajouts de ce cycle (mise à jour corrective)

- **Correctif de la boîte de dialogue de changement de framework** : la commande de redémarrage utilise désormais la forme standard à titre vide `start "" <programme>` ; auparavant `start MikanCL <programme>` traitait `MikanCL` comme le nom du fichier à exécuter, ce qui affichait « Windows ne trouve pas le fichier 'MikanCL' » ; le redémarrage en mode source passe par `run.py` (le projet n'a pas de `mc_launcher/__main__.py`)
- **Fermeture accélérée** : un clic sur fermer écrit d'abord la configuration sur disque, puis termine directement le processus, en sautant le recyclage de l'environnement WebView2 ; la sortie ne bloque plus 1 à 2 secondes
- **Fond en mode clair** : la plaque de fond de la fenêtre et la couleur de fond pywebview suivent le basculement clair/sombre ; en journée, un fond clair est utilisé et un « tableau noir » sombre ne transparaît plus
- **Couleur de police personnalisée** : dans Paramètres → Apparence, ajout d'un nuancier « Couleur de police » permettant de personnaliser la couleur du texte courant ou de revenir d'un clic à « Suivre le thème » ; après modification, le texte atténué et la sélection de couleur sont rafraîchis en même temps et le réglage est persisté avec la configuration
- **Correctif des packs de skins pour versions récentes** : la cause racine est que la vanilla 1.19.4+ possède 9 skins par défaut attribués selon l'UUID du joueur, alors que l'ancien pack de ressources ne couvrait que steve / alex ; désormais les 9 noms de skins par défaut sont tous écrits avec le même skin dans les deux répertoires `player/wide` et `player/slim`, de sorte que n'importe quel UUID trouve le skin
- **Logique de remplacement automatique du pack de skins** : ne saute plus sur « la présence d'un MikanCL-*.zip quelconque suffit », mais valide selon « empreinte du contenu du skin + modèle de bras + pack_format de la version + emplacement réel du pack » ; après un changement de skin ou une mise à niveau de version, le pack est réécrit automatiquement ; le bouton de complétion des manques vérifie avant d'écrire et distingue « mis à jour / déjà à jour »
- **Import du pack de skins vers une version spécifique** : la carte du pack de skins de la version embellie ajoute une liste déroulante de versions et « Importer un pack de skins… », permettant d'importer directement dans le répertoire isolé de la version installée choisie (la liste déroulante de versions existante de la version classique reste utilisable)
- **Correctif des « skins récents » de la page d'accueil** : auparavant, la vignette ne traitait que `data-skin`, et le `data-skin-path` utilisé par la page d'accueil n'était pas rendu, d'où des cartes vides ; désormais le découpage de la tête est unifié et les sources « bibliothèque de skins + skin du compte courant + PNG sous data/skins » sont fusionnées, ce qui permet l'affichage même lorsque la bibliothèque de skins est vide
- **Skins récents sur la page d'accueil de la version classique** : la page d'accueil de la version classique ajoute une carte « Skins récents », cohérente avec la version embellie ; un clic permet de changer de skin et de s'adapter automatiquement à la version installée

## Centre de contenu et détection d'instances (ce cycle)

- **Choix de la version de jeu avant le détail du Mod** : un clic sur un projet n'affiche plus directement toutes les versions, mais regroupe d'abord par version de Minecraft prise en charge ; après choix d'une version, seuls les Jar disponibles pour cette version sont chargés et présentés par groupes « stable / bêta », avec type de version, chargeur, date et taille indiqués sur la ligne de fichier
- **Vérification des dépendances préalables** : après l'entrée dans la liste de fichiers, les noms et icônes des dépendances obligatoires sont analysés automatiquement ; les dépendances manquantes ou nécessitant une installation supplémentaire sont cliquables pour y accéder directement ; lors de l'installation, les dépendances obligatoires sont toujours complétées automatiquement
- **Catégories de recherche à la PCL** : le centre de contenu ajoute des catégories d'usage « Tout / Optimisation / Technique / Magie… » et prend en charge le filtrage combiné par source, chargeur et version de jeu ; les types sont séparés en Mod, modpack, pack de ressources, pack de textures et pack de shaders
- **Séparation des packs de textures et des packs de ressources** : les types de recherche et les libellés distinguent radicalement pack de ressources (resourcepack), pack de textures (texturepack) et pack de shaders (shader), sans plus confondre les trois
- **Code de partage du multijoueur Terracotta** : la page multijoueur de la version embellie ajoute la création de salle, l'entrée dans une salle, la fin du multijoueur et « Copier le code de partage » ; après création, l'état de la salle est interrogé automatiquement et le code de salle est affiché dans la carte ; avant l'entrée, le format du code de salle est normalisé automatiquement
- **Détection automatique du répertoire de données** : lors de l'ajout d'un répertoire de données, le niveau racine `.minecraft`, le répertoire `versions` ou un dossier de version unique sont identifiés automatiquement et le répertoire correspondant est sélectionné ; même sans JSON de version, un dossier de version qui contient un Jar de jeu apparaît dans « Versions installées » sous son nom de dossier (effet simultané sur la version classique et la version embellie)

## Mode d'empaquetage (ce cycle)

- **exe monofichier** : `python build_exe.py` passe à PyInstaller onefile ; PySide6, pywebview, toolbelt et les ressources front-end sont tous intégrés dans un seul `MikanCL.exe`, un seul fichier suffit à la distribution ; au premier lancement, le runtime est d'abord décompressé, ce qui prend quelques secondes de plus qu'en onedir
- **Pourquoi PyInstaller (pyi)** : Nuitka n'est pas encore adapté à Python 3.15 et ne peut pas compiler dans cet environnement ; PyInstaller prend déjà en charge Python 3.15, la v5.2.0 est donc empaquetée avec PyInstaller, sans impact sur les fonctionnalités ni le comportement d'exécution

## Framework d'interface

- **Choix initial entre deux frameworks** : au lancement, une boîte de dialogue Qt légère explique les différences entre la version classique et la version embellie ainsi que les fonctionnalités manquantes ; après choix, seul le framework correspondant est chargé, l'autre ne consomme pas de mémoire
- **La version embellie passe à pywebview + Edge WebView2** : barre latérale en tuiles de verre, cartes de verre flottantes, bouton de lancement dégradé, panneau de thème et skins récents ; rendu Chromium, l'aspect visuel se rapproche des principaux lanceurs de référence
- **Distribution de WebView2 Runtime** : détection via le registre + le répertoire d'installation ; en cas d'absence, une boîte de dialogue guide le téléchargement ; prise en charge d'une version fixe intégrée dans le répertoire d'installation `webview2/` (`WEBVIEW2_RUNTIME_PATH`) ; en cas d'échec de rendu, un message s'affiche et le retour immédiat à la version classique est possible
- **Basculement bidirectionnel des frameworks** : la version classique et la version embellie partagent la même configuration, les mêmes comptes, instances et noyau de téléchargement ; « Paramètres → Apparence → Framework d'interface » permet de basculer à tout moment de l'un à l'autre (`switch_frame` + redémarrage automatique), sans plus verrouiller le framework ; le `frame_locked` des anciennes configurations devient automatiquement sans effet
- **Verre dépoli et polices** : la version embellie passe entièrement au verre dépoli semi-transparent (`backdrop-filter`, barre latérale / barre de titre / barre d'état / cartes / panneaux superposés uniformément vitrifiés) ; la couleur de thème est superposée en teinte claire sur le verre dépoli et suit le changement de thème ; la police passe à `Microsoft YaHei UI`, taille 13.5px, interligne 1.55, avec restauration du rendu sous-pixel ClearType sous Windows et correction du flou des petites tailles ; les cartes graphiques modestes peuvent désactiver d'un clic le verre dépoli et les animations dans les paramètres

## Alignement des fonctionnalités

- **Toutes les pages** : contrat utilisateur, page d'accueil, centre de téléchargement (versions de jeu / chargeurs / Java / édition Bedrock / accélérateur de téléchargement / tâches), centre de contenu (Modrinth / CurseForge), gestionnaire d'instances, comptes et skins, multijoueur, boîte à outils, centre de tutoriels, navigateur intégré et paramètres sont entièrement utilisables dans la version embellie
- **Téléchargements partagés** : jeux, chargeurs, contenu, Java, édition Bedrock et modpacks passent par le même téléchargeur multithread, avec prise en charge de la pause / annulation / reprise de téléchargement et d'une limite de concurrence ; la version embellie ajoute un onglet « Accélérateur de téléchargement » : coller un lien direct quelconque suffit à télécharger avec le même téléchargeur segmenté, jusqu'à 328 threads
- **Alignement du processus de lancement** : une checklist complète est exécutée avant le lancement (Java, mémoire ne dépassant pas 70 % de la mémoire physique, conflits de Mods, espace disque > 2 GB, avertissement en cas de carte graphique intégrée + pack de shaders) ; les éléments bloquants exigent une confirmation de l'utilisateur pour forcer le lancement ; prise en charge du lancement séquentiel par sélection multiple, de l'export de scripts de lancement bat / ps1 / sh, de l'isolation de version et de la sauvegarde automatique du monde avant lancement
- **Système de comptes** : compte hors ligne, connexion Microsoft par code d'appareil, connexion authlib-injector ; import de skin, changement rapide et bascule de modèle Steve/Alex
- **Atelier de skins** : la version embellie ajoute un canevas pixel 64×64 (pinceau / gomme / remplissage / pipette / annuler) et un aperçu 3D de skin en CSS 3D (rotation par glisser, zoom à la molette) ; l'enregistrement ajoute à la bibliothèque et applique ; le pack de skins prend en charge le joueur, la version, le modèle de bras et le PNG de cape
- **Paramètres de version** : la page d'instance permet de modifier directement la mémoire d'une version, l'isolation, la priorité de processus, le titre de fenêtre, les arguments JVM / de jeu supplémentaires et la connexion automatique au serveur ; la liste des Mods prend en charge activer / désactiver / supprimer ; les instances prennent en charge le déplacement vers le haut / vers le bas avec persistance
- **Outils de contenu et de données** : galerie de captures d'écran (aperçu / export Zip / suppression), rapport de plantage (consultation / copie du résumé / suppression), aperçu du terrain par graine (réutilise le programme Java de bruit de Perlin vanilla), éditeur NBT (arbre de types + modification des feuilles + .bak automatique)
- **Boîte à outils** : analyse des dépendances et complétion, composants tiers, graphe de dépendances des mods (mise en évidence des dépendances manquantes et des dépendances circulaires), sauvegarde / restauration de monde, journaux, import de modpacks et de HMCL/PCL, nettoyage du cache
- **Multijoueur** : ajout / suppression dans la liste de serveurs, Minecraft Server List Ping, connexion au démarrage, installation / démarrage / arrêt du multijoueur Terracotta
- **Tutoriels et navigateur** : le centre de tutoriels lit les Markdown selon la langue de l'interface (9 articles intégrés, complétés automatiquement s'ils manquent) ; le navigateur intégré est une fenêtre WebView2 indépendante qui lit directement les vidéos de Bilibili
- **Gestion des fichiers de contenu** : la page d'instance ajoute trois catégories d'onglets Mods / packs de ressources / packs de shaders, avec prise en charge d'activer / désactiver / supprimer / ouvrir le répertoire, conformément à la convention `.disabled` de la version classique
- **« Enregistrer sous »** : la version embellie complète toutes les entrées « Enregistrer sous » de la version classique — la page de détail du contenu permet de télécharger sans installer (Mod / modpack / pack de ressources / pack de shaders), la ligne de version de la page de téléchargement permet d'enregistrer séparément le Jar client vanilla, la page de chargeur permet d'enregistrer séparément l'installateur officiel Forge / NeoForge / Fabric / Quilt / LiteLoader, tout passant par un téléchargement segmenté multithread vers le dossier choisi par l'utilisateur
- **Alignement du centre des tâches** : les tâches échouées / annulées ajoutent « Réessayer », qui relance avec les paramètres d'origine ; conservation de pause / reprise / annulation / nettoyage des tâches terminées et des détails d'erreur
- **Réparation d'instance** : la page d'instance ajoute « Réparer l'instance », qui vérifie et complète d'un clic les fichiers vanilla et de chargeur, puis met à jour automatiquement l'enregistrement de version de l'instance
- **Liste de versions de la page d'accueil** : ajout d'un champ de recherche de version (affiché à partir de 6 versions) et du tri par glisser-déposer ; le résultat du tri est écrit dans `config.version_order` et s'applique simultanément à la version classique et à la version embellie
- **Correctif de l'analyse du manifeste de versions** : la page de téléchargement de la version embellie n'analysait pas l'enveloppe de cache du manifeste, ce qui vidait la liste des versions vanilla et empêchait l'installation ; c'est corrigé, l'installation vanilla / chargeur fonctionne de nouveau normalement
- **Export de modpack** : la page d'instance ajoute « Exporter le modpack », permettant d'empaqueter en sauvegarde privée `.mikan` ou en zip de modpack CurseForge avec `manifest.json` (incluant mods / packs de ressources / packs de shaders / config / options.txt)
- **Alignement de la page de paramètres** : ajout de la gestion des sources de téléchargement (ajouter / modifier / supprimer / activer / définir comme actuelle / test de connectivité, partagée avec la version classique via `config.sources`), des sources de contenu et miroirs (CDN Modrinth, CurseForge API Key / CDN), des comptes et de la connexion (Microsoft OAuth Client ID, adresse authlib-injector), de la gestion par zones du répertoire de données, des arguments JVM supplémentaires, du titre de fenêtre et de l'interrupteur d'animation de lancement
- **Paramètres** : thème (avec import / export JSON et changement), image de fond, langue, mémoire, Java, mode d'isolation, threads (1~328), limitation de vitesse, proxy, interrupteurs d'optimisation du jeu, préchargement JVM, interrupteurs de modules fonctionnels, réduction en icône lors de la fermeture, sauvegarde et consultation du contrat ; le changement de langue de l'interface synchronise le contrat et le contenu des tutoriels
- **Contrat utilisateur mis à niveau vers 1.7** : ajout de la possibilité de basculer dans les deux sens entre les deux frameworks avec partage des mêmes données, du rendu du verre dépoli respectivement par WebView2 (Chromium) et DWM, et de l'optimisation des polices via ClearType ; synchronisé en 5 langues (chinois / anglais / russe / français / japonais)

## Fenêtre, extensions et fonds d'écran

- **Redimensionnement de la fenêtre sans bordure** : les quatre côtés / quatre coins de la version embellie permettent de redimensionner la fenêtre par glisser, un double-clic sur la barre de titre maximise, taille minimale 960×600 ; le redimensionnement passe par l'API de fenêtre Win32 et reste aligné sur le déplacement de la souris sous mise à l'échelle DPI
- **Mécanisme d'extension (plugin)** : les paramètres ajoutent une page « Extensions » prenant en charge l'import de packs `.zip` / `.mikan-ext`, l'activation / désactivation / suppression, l'ouverture du répertoire d'extensions et l'actualisation ; une extension activée ajoute une entrée dans la barre latérale, sa page s'exécute dans un iframe sandbox et peut appeler les interfaces de pont du lanceur via `postMessage` (comptes, versions, téléchargements, fichiers, etc.) ; les plugins Python sous `data/plugins` de la version classique sont également listés
- **Fond d'écran animé** : la version embellie prend en charge la lecture en boucle muette de vidéos MP4 / WebM et d'animations GIF / WebP, avec un service média local intégré gérant Range et démarré à la demande, et une pause automatique lorsque la fenêtre passe en arrière-plan ; la version classique prend en charge les fonds animés GIF / WebP (QMovie image par image sur toute la fenêtre), partageant les mêmes paramètres que l'image de fond statique
- **Zoom du canevas de l'atelier de skins** : le canevas prend en charge un zoom 2×–12× et une zone défilante, permettant de faire défiler jusqu'aux pixels des jambes et pieds dans une petite fenêtre ou à fort zoom, corrigeant l'impossibilité précédente de peindre les pieds ; le canevas de la version classique est également placé dans une zone défilante, avec défilement possible après agrandissement 6×/8×

## Barre latérale et thèmes

- **Barre latérale à icônes verticales** : la barre latérale passe à une colonne unique d'icônes verticales, n'affichant par défaut que les icônes et ne faisant apparaître le nom à droite qu'au survol ; la zone de contenu n'est plus comprimée horizontalement et la barre latérale elle-même devient défilante en cas d'entrées trop nombreuses
- **Thèmes multiples** : ajout de 8 thèmes intégrés (vert forêt / bleu océan / violet crépuscule / cramoisi / ambre / cyan-jade / rose sakura / bleu nuit polaire), toute la palette étant remplacée de façon synchronisée et pas seulement la couleur d'accentuation
- **API de thème personnalisé** : placer `data/themes/*.json` ou importer via la page de paramètres ; export de modèle pris en charge ; les plugins peuvent appeler `themes.register()` pour un enregistrement dynamique ; le vert forêt par défaut conserve l'effet de rotation de teinte existant
- **Changement rapide de skin** : les skins importés sont automatiquement ajoutés à la bibliothèque (déduplication par sha1, priorité aux plus récents, 60 entrées maximum) ; un clic sur l'avatar de la barre latérale ouvre le menu « Skins récents », avec changement en un clic / import / ouverture de la bibliothèque de skins

## Verre dépoli du bureau et navigation en tuiles

- **Vrai verre dépoli transparent sur le bureau** : les paramètres ajoutent « Transparence sur le bureau (vrai verre dépoli) » ; le fond de fenêtre, composé par DWM, laisse réellement transparaître le bureau du système (Win11 utilise `DWMWA_SYSTEMBACKDROP_TYPE=3`, Win10 revient à `SetWindowCompositionAttribute` en acrylique) ; une fois activé, l'image de fond et le fond animé sont automatiquement ignorés et la lecture vidéo mise en pause ; désactivé, le fond d'origine est immédiatement restauré
- **Réglage de l'intensité du verre dépoli** : un curseur 0–100 contrôle en temps réel le rayon de flou, la concentration de teinte et la transparence des cartes ; dans la version embellie, le glissement donne un aperçu immédiat ; la version classique propose le même curseur dans « Paramètres → Effets d'interface », les deux interfaces partageant la configuration `glass_strength`
- **Tuiles de verre à la Windows 8** : la barre latérale est une colonne unique de tuiles de verre verticales, icônes centrées, texte masqué par défaut, nom apparaissant en survol avec soulèvement, état sélectionné avec contour de thème ; l'ombre est en deux couches « projection externe + reflet interne », conservant une hiérarchie nette sur fond de verre ; la version classique passe également à une colonne d'icônes de 84px + ToolTip

## Correctifs

- **Écran noir au lancement** : la fenêtre de la version embellie est créée masquée + transparente et n'est affichée qu'une fois le premier rendu terminé, moment où le verre DWM est appliqué, évitant ainsi le clignotement d'un fond noir
- **Plantage des paramètres de version** : correction de `version_settings` qui levait `NameError: name 'ISOLATION_LABELS' is not defined`
- **Découpage de l'avatar** : le skin 64×64 entier n'est plus inséré dans le cadre d'avatar ; la tête est découpée selon la position des pixels (deux couches : visage + chapeau), de façon cohérente dans la barre latérale, la page d'accueil, la page de compte et la liste des skins récents
- **Recouvrement en un clic du pack de skins** : ajout de « Installation par recouvrement en un clic », qui nettoie d'abord les anciens packs de skins de chaque répertoire de jeu avant d'écrire le skin courant, avec prise en charge du nom de joueur, de la version, du modèle de bras et de la cape

## Correctifs et compléments de ce cycle

- **Déplacement de la fenêtre limité à la barre de titre** : la version embellie désactive l'`easy_drag` sur toute la fenêtre de pywebview et utilise la drag-region native de pywebview (`DRAG_REGION_SELECTOR=.pywebview-drag-region`) ; seule la partie gauche de la barre de titre est déplaçable et les contrôles comme le curseur d'intensité du verre dépoli retrouvent un glissement normal ; un double-clic sur la barre de titre bascule le mode maximisé
- **Correctif du menu contextuel sans réaction au clic** : le menu intercepte lui-même `pointerdown` sans propagation, évitant que l'écouteur de fermeture de `document` ne retire le menu avant la distribution du `click` ; la boîte de confirmation passe au `ask` intégré, évitant que WebView2 ne bloque le `confirm` natif
- **Le verre dépoli laisse réellement transparaître le bureau** : le scrim des pages embellies passe de `.42/.56` à `.04/.10`, et la barre latérale / barre supérieure / barre d'état / cartes utilisent `--glass-a` / `--glass-a2` pilotés par l'intensité (les cartes conservent une teinte minimale pour que le texte reste lisible devant un fond blanc) ; le basculement de l'interrupteur ou de l'intensité rappelle systématiquement `glass_apply` côté backend, avec effet immédiat également en version empaquetée
- **Correctif du désalignement de l'interface** : ajout de pages en flux `.flow`, où les cartes s'étendent naturellement selon le contenu et ne sont plus écrasées par flex ; la boîte à outils (complétion des dépendances), le gestionnaire d'instances et la page multijoueur passent au défilement sur toute la page, les listes d'instances / de serveurs défilant séparément avec une hauteur limitée
- **Double-clic d'installation rapide dans la liste de téléchargement** : dans le centre de téléchargement de la version embellie, un double-clic sur une ligne de version vanilla (ou un clic sur « Détails ») ouvre les détails d'installation, où l'on peut choisir vanilla / Fabric / Quilt / Forge / NeoForge / LiteLoader / Forbric et sélectionner la version du chargeur, le tout en un seul téléchargement-installation, sans avoir à repasser ensuite par la page de chargeur ; Forbric valide toujours strictement 26.2
- **Changement rapide d'instance sur la page d'accueil** : à côté de la liste déroulante de versions de la page d'accueil, ajout d'une liste déroulante d'instances ; le changement bascule immédiatement le répertoire de données et actualise la liste de versions
- **Entrée des paramètres de version** : le détail de version et le menu contextuel ajoutent « Paramètres de version », permettant de configurer mémoire, mode d'isolation, priorité de processus, titre de fenêtre, arguments JVM / de jeu supplémentaires, serveur et port de connexion automatique, avec des champs identiques à la version classique
- **Correctif de la localisation de PowerShell pour l'édition Bedrock** : en cas de PATH tronqué, retour à `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`, avec repli sur `OSError`, évitant que l'interface du répertoire Bedrock ne lève `FileNotFoundError`
- **Complément du sous-menu de détail de version** : dans la liste de versions de la version embellie, un clic sur `›` ou un clic droit ouvre le détail de version, comprenant lancement / répertoire de jeu / répertoire de version / répertoire Mods / suppression, type de chargeur (6 types) et liste déroulante de versions, installation ou changement de chargeur, enregistrement de l'installateur, activation / désactivation / suppression dans la liste des Mods et avertissements de conflit ; le menu contextuel complète l'ouverture du répertoire de jeu / de version / des Mods et la copie de l'ID de version
- **Correctif de l'affichage des versions de chargeur** : la liste déroulante de la version embellie récupère à nouveau les versions selon la version MC courante et réaffiche correctement `selected`, en vidant l'ancienne version lors d'un changement de chargeur ou de MC ; la version classique supprime les valeurs par défaut codées en dur `0.16.10 / 49.1.0`, laissant vide pour installer la dernière version stable, et la version MC du détail courant est reprise automatiquement
- **Suppression des tâches de téléchargement (des deux côtés)** : chaque ligne du centre de téléchargement ajoute « Supprimer la tâche », qui annule d'abord puis retire une tâche en cours (sans supprimer les fichiers déjà téléchargés) ; la version embellie passe par `task_delete`, la version classique par `DownloadManager.remove`
- **Import de skin avec type de bras et recouvrement** : le panneau d'import de la version embellie propose des boutons radio Steve / Alex et une case « Recouvrir toutes les versions installées » ; le changement rapide de skin réutilise le modèle enregistré. Après import ou changement, les versions installées sont analysées automatiquement et un pack de skins adapté est généré pour chacune via `resolve_game_dirs(...).skin_targets()` ; lors de l'installation ultérieure d'une nouvelle version / d'un modpack, `_auto_skin` effectue automatiquement le complément, sans recouvrement manuel. La page de compte de la version classique ajoute également la case de recouvrement avec adaptation automatique, et le changement rapide de skin depuis la barre latérale écrit aussi automatiquement dans chaque version
- **Isolation totale par défaut** : la valeur par défaut de `isolation_mode`, le défaut de `from_dict` et le repli sur valeur invalide passent tous à `all` ; les versions nouvellement installées utilisent par défaut le répertoire indépendant `versions/<id>/game`
- **Débordement de contenu transformé en défilement** : le `.stage` de la version embellie passe à `overflow-y:auto` avec ajout d'une barre de défilement fine ; les contenus longs comme les tâches de téléchargement, les paramètres et le détail de version ne sont plus comprimés ; dans la version classique, les pages sont déjà dans un `QScrollArea` et la barre latérale en colonne d'icônes ne comprime plus le contenu principal
- **Barre latérale verticale en colonne unique** : la barre latérale de la version embellie fait 68px de large, en colonne unique d'icônes + nom apparaissant au survol (`.nav-tip`) ; celle de la version classique fait 84px, avec `ToolButtonIconOnly` en icônes 48×48 et ToolTip conservé, de façon cohérente des deux côtés

## Performances et build

- **Import paresseux** : QtWebEngine, la fenêtre principale, le centre de contenu et le module réseau sont importés à la demande selon le framework ; lorsque la version embellie est choisie, QtWebEngine est totalement ignoré
- **Empaquetage passé à PyInstaller onedir** : plus de décompression à chaque lancement, collecte automatique des assemblys d'interopérabilité pywebview / pythonnet / WebView2 ; distribution du répertoire `MikanCL` entier
- **Compatibilité** : ajout des options de configuration `frame_mode`, `frame_mode_asked`, `frame_locked` ; les anciennes configurations reviennent par défaut à l'interface Qt classique, sans migration manuelle ; le numéro de version est fixé à **5.1.0**, README / RELEASE / i18n synchronisés
- **Correctif de l'injection d'interface** : les objets Window / Config de js_api sont marqués `_serializable = False`, évitant que pywebview ne parcoure récursivement les objets COM natifs de WebView2 lors de l'injection, ce qui retardait voire faisait échouer l'injection (hors mode débogage, un « backend pas encore prêt » s'était produit) ; le front-end interroge désormais `window.pywebview.api` en boucle jusqu'à ce qu'il soit prêt, rendant le premier lancement plus stable
- **Détails du premier démarrage** : à côté de la liste déroulante de versions de la page d'accueil, ajout d'une liste déroulante de répertoires de données (affichée à partir de 2 répertoires), avec actualisation immédiate de la liste de versions après changement ; la liste Java affiche uniformément les informations de bits

---

# MikanCL v5.0.0 — Notes de version

Date de publication : 2026-11-07

## Interface

- **Navigation en tuiles** : la navigation de gauche passe entièrement à des tuiles de style iOS / Bakaxl (3 colonnes, icône + libellé court), la barre latérale est élargie à 244px, et l'état sélectionné utilise un contour vert de thème
- **Refonte du verre dépoli** : `WA_TranslucentBackground` est toujours défini avant la création de la fenêtre ; Windows 11 utilise l'acrylique système DWM (`DWMWA_SYSTEMBACKDROP_TYPE=3`), Windows 10 revient à BlurBehind ; la cause racine est que le changement de l'attribut de transparence en cours d'exécution ne prenait pas effet dans l'ancienne version, et qu'AcrylicBlurBehind rendait le texte flou. Une fois activé, le fond est entièrement en verre dépoli, les cartes / boutons sont en matière blanche semi-transparente tout en conservant la couleur d'accentuation du thème, **désactivé par défaut**
- **Correctif des saccades lors du changement de page** : suppression de la rastérisation hors écran de la page entière causée par l'ajout de `QGraphicsOpacityEffect` à `QScrollArea` (source de saccades et de flou du texte) ; le rafraîchissement de page passe à `QTimer.singleShot(0, ...)` exécuté au repos, et un clic répété sur la tuile courante ne rafraîchit plus inutilement

## Ajouts

- **Rappel de la version officielle** : tous les 10 lancements de jeu, un message « Soutenez la version officielle ! » s'affiche, avec deux options « La prochaine fois » et « Je vais l'acheter » ; la seconde ouvre la boutique officielle et fournit une entrée d'achat de la version officielle
- **Complément de l'analyse Java** : couverture des répertoires des différentes distributions dans Program Files, d'Oracle javapath, du registre (y compris WOW6432Node), du PATH, des JDK fournis par scoop / chocolatey / gradle / l'IDE, du runtime .minecraft, des répertoires HMCL / PCL et des chemins courants des disques C à F ; une même version majeure est affichée repliée par défaut, et un clic droit sur « Voir toutes les versions Java » permet de déplier
- **Vérification des mises à jour CurseForge** : `check_mod_updates()` ajoute la correspondance CurseForge `/mods/fingerprint` (empreinte Murmur2) en plus du SHA1 de Modrinth ; « Vérifier les mises à jour » ne saute plus la moitié des Mods
- **Gestion des mondes + sauvegardes** : les paramètres de version ajoutent un tableau des mondes (monde / mode de jeu / dernière session / taille), avec sauvegarde du monde sélectionné / de tous, restauration de sauvegarde et ouverture du répertoire de sauvegardes ; sauvegarde automatique avant lancement en option (déduplication dans la même minute pour un même monde, 20 copies maximum conservées)
- **Ping de la liste de serveurs** : utilisation du protocole Minecraft Server List Ping (avec repli legacy) pour afficher la latence, le nombre de joueurs en ligne, le MOTD, la version et l'icône du serveur, sans plus dépendre d'une API tierce
- **Export de script compatible Linux/macOS** : ajout de la génération `.sh` (`#!/usr/bin/env bash`, chmod 755 automatique)
- **Capes et élytres** : le pack de skins / l'atelier de skins prend en charge l'import de capes 64×32, écrites dans `CustomSkinLoader/LocalSkin/capes`, l'aperçu 3D pouvant basculer entre forme cape et forme élytre
- **Auto-diagnostic hors ligne** : au lancement, le manifeste de versions et les sources miroirs sont sondés ; hors connexion, « Aucune connexion réseau actuelle » s'affiche et les fonctions en ligne sont grisées dans la navigation
- **Santé de l'instance** : agrégation de la corruption de version, des fichiers manquants, des conflits de Mods / dépendances manquantes et de la surallocation de mémoire, affichée en vert / jaune / rouge dans la vue d'ensemble de la version
- **Limitation de vitesse de téléchargement** : les paramètres ajoutent une limite de bande passante globale (KB/s, 0 = illimité), appliquée à tous les threads de téléchargement via un seau à jetons global
- **Complétion des dépendances manquantes en un clic** : la page des dépendances ajoute « Compléter les dépendances manquantes », qui recherche automatiquement le modid sur Modrinth et installe la dernière version compatible
- **Opérations par lots sur plusieurs instances** : ajout de la vérification de santé par lots, de la complétion de fichiers par lots et de l'export de configuration d'instance par lots

## Architecture

- **ModpackPipeline** : le `ModpackDropWorker` de `dropinstall.py` et le `ContentInstallWorker` de `page_content.py` sont fusionnés en un seul pipeline « version de base → chargeur → validation JSON → overrides »
- **resolve_game_dirs** : la détermination du répertoire isolé est regroupée dans `GameDirs` (répertoire principal + répertoire isolé + cibles d'écriture des skins / mods / sauvegardes de monde), appelée uniformément par les skins, la page de fichiers et l'import, éliminant la logique dupliquée « en isolation totale, le skin doit être écrit deux fois »

## Documentation et build

- Le contrat utilisateur passe à la version 1.5 : ajout de l'explication de la vérification par empreinte et de la clause de non-responsabilité sur les sauvegardes de monde
- Le centre de tutoriels ajoute « Prise en main rapide du lanceur : de zéro à l'entrée en jeu », couvrant chaque étape
- Le script d'empaquetage passe à **Nuitka** (`python build_exe.py`, compilation en C, démarrage plus rapide), avec mise à jour des traductions i18n
- Compilation : `python -m compileall mc_launcher` passe ; le test de fumée hors écran crée la fenêtre principale et parcourt toutes les pages sans anomalie

---

# MikanCL v4.9.4 — Notes de version

Date de publication : 2026-11-06

## Correctifs

- **Ghosting de texte lors du défilement à la molette en mode verre dépoli** : une fois « Verre dépoli » activé, le fond de fenêtre est semi-transparent ; lors du repaint partiel de Qt, le contenu de l'ancienne image n'était pas effacé, si bien qu'après défilement les titres et corps de cartes se superposaient au nouveau contenu en deux couches de texte (dans le répertoire de données par défaut de l'exe empaqueté, le verre dépoli est activé, alors qu'il est désactivé dans le répertoire source, ce qui explique que le problème n'apparaissait que sur l'exe). Désormais, le conteneur racine recouvre uniformément la zone sale avec la couleur de fond via `CompositionMode_Source` (`rgba(12,19,16,170)` en verre dépoli semi-transparent, `#0c1310` opaque en mode normal) ; chaque image est dessinée à partir d'un fond propre, et ni le défilement ni le changement de page ne laissent de texte résiduel

## Build et vérification

- Reproduction : avec l'ancien exe (verre dépoli activé), après défilement à la molette, le texte des cartes de page apparaissait en deux couches superposées
- Vérification : exécution depuis les sources avec verre dépoli forcé, 3 défilements continus avec captures image par image, page propre sans ghosting ; l'exe réempaqueté, en verre dépoli activé, a également été défilé et capturé en continu, sans superposition de texte
- Compilation : `python -m compileall mc_launcher` passe (code de sortie 0)
- Artefact : `dist/MikanCL.exe`, 220,358,419 octets ≈ 210.2 MB (2026-11-06 14:09:00), fichier unique avec toutes les dépendances intégrées

---

# MikanCL v4.9.3 — Notes de version

Date de publication : 2026-11-06

## Ajouts

- **Prise en charge des installateurs officiels (EXE / MSI) dans le centre Java** : la barre d'outils ajoute une liste déroulante « Mode d'installation » permettant de basculer entre « ZIP portable » et « Installateur officiel ». Temurin / Azul Zulu / Amazon Corretto récupèrent directement la liste des versions d'installateur depuis l'API officielle, puis appellent `msiexec` / l'assistant EXE pour terminer l'installation après téléchargement (une demande d'élévation UAC peut apparaître) ; à la fin, une nouvelle analyse est lancée automatiquement et le Java nouvellement installé s'affiche ; les distributions sans installateur ne conservent que l'option ZIP
- **Écriture automatique du ZIP portable dans le PATH utilisateur** : une fois la version portable décompressée et la détection réussie, le répertoire `bin` de Java est automatiquement écrit dans `HKCU\Environment\Path` (sans ajout répété s'il existe déjà), le PATH du processus courant est mis à jour et `WM_SETTINGCHANGE` est diffusé, permettant un appel direct depuis la ligne de commande, les autres lanceurs et le jeu
- **Section « Dossier de versions » sur la page d'accueil** : sous la liste de versions, ajout d'une liste déroulante de sections et d'un menu « Nouveau / Choisir… », permettant d'enregistrer directement n'importe quel dossier de la machine comme nouveau répertoire de versions (un sous-répertoire `versions/` est créé automatiquement à la création) ; après changement, la liste de versions, les mods et les sauvegardes de monde passent par le nouveau répertoire, sans interférer avec les instances de modpacks
- **Bouton flottant circulaire de téléchargement en bas à droite** : dès qu'une tâche de téléchargement existe (y compris en file d'attente), un bouton circulaire apparaît en bas à droite ; un clic gauche ouvre le centre de téléchargement, un clic droit revient à la page précédant l'entrée dans le centre de téléchargement (historique de 20 sauts de page conservé), et le bouton se masque automatiquement lorsque toutes les tâches sont terminées

## Correctifs

- **Mauvais userType dans le script de lancement exporté pour la connexion authlib-injector** : lors de l'export du script de lancement, les comptes authlib-injector étaient uniformément écrits en `--userType msa` ; désormais les comptes Microsoft utilisent `msa`, la connexion authlib-injector et les comptes hors ligne utilisent `legacy`, et les paramètres `-javaagent` et `--authServer` d'authlib-injector sont complétés, permettant au script exporté d'entrer directement dans le serveur de vérification
- **Texte de la page d'accueil après la sortie de l'édition Bedrock** : de retour sur la page d'accueil après la fin du lancement de l'édition Bedrock, `Démarrage : __bedrock__` ne s'affiche plus ; c'est « Édition Bedrock {version} » qui s'affiche
- **La déduplication des instances ignorait l'instance par défaut** : la page d'installation par téléchargement et l'installation de modpack passent à `instance_list()` (incluant l'instance par défaut construite dynamiquement) ; une même version / un même répertoire installé en double ne génère plus d'instance dupliquée
- **La mémoire ajustée au clavier n'était pas enregistrée** : le curseur de mémoire écrit désormais la configuration dès `valueChanged` avec écriture disque anti-rebond ; un ajustement par flèches / PageUp / PageDown n'est plus perdu après redémarrage
- **Le bouton d'annulation ne fonctionnait plus après une nouvelle tentative** : les rappels d'annulation des tâches d'installation de contenu et d'enregistrement sous sont désormais liés au thread de téléchargement créé à chaque fois (`task.cancel` / `task.pause_event`) ; échec → nouvelle tentative → annulation peut maintenant réellement interrompre le nouveau thread
- **Nettoyage du cache incomplet** : le nettoyage des caches de couverture / de téléchargement supprime désormais récursivement les sous-répertoires (`shutil.rmtree`), sans laisser de répertoires imbriqués
- **Anomalie de lecture des fichiers de skin** : la sélection d'un skin local et l'application du pack de skins capturent toutes deux `OSError` (absence de permission de lecture, fichier verrouillé) et affichent une boîte de dialogue au lieu de lever une traceback dans la console
- **Fin de page omise à la fermeture** : `closeEvent` complète la page de l'accélérateur de téléchargement, la page de l'atelier de skins et la page de graine de monde ; le thread de terrain par graine est attendu, évitant `QThread: Destroyed while thread is still running`
- **Fausse détection de la coloration des journaux** : les mots-clés d'erreur / d'avertissement passent à une expression régulière avec limites de mots ; les journaux normaux comme `mirror` ou « non échoué » ne sont plus marqués en rouge, et `[ERROR]` est correctement identifié
- **Divers** : la recommandation Java dans la boîte de dialogue de plantage de la page d'accueil passe à Temurin spécifiquement ; suppression de la branche `getattr(ctx, "installer")` qui ne pouvait jamais se produire ; la couleur de fond du verre dépoli passe d'un rougeâtre à un vert-noir cohérent avec le thème ; le caractère du bouton maximiser devient le plus générique `▣` ; suppression de `page_loader.py`, référencé par aucun module

## Build et vérification

- Compilation : `python -m compileall mc_launcher` passe intégralement (code de sortie 0)
- Fumée : construction hors écran de la fenêtre principale, 21 vérifications toutes réussies — masquage / apparition / masquage du bouton flottant de téléchargement, historique de saut de page et retour par clic droit, bascule de `game_path` après enregistrement du dossier de versions, liste déroulante du mode d'installation Java (Temurin 2 entrées / Microsoft ZIP uniquement), texte de lancement de l'édition Bedrock, trois exemples de regex de niveau de journal, nettoyage récursif du cache
- En ligne : Temurin 21 a récupéré `OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.msi`, Azul 21 a récupéré `zulu21.54.109-ca-jdk21.0.13.0.3-win_x64.msi`, Corretto 21 a récupéré `amazon-corretto-21.0.13.0.11-windows-x64.msi`
- Artefact : `dist/MikanCL.exe`, 220,358,041 octets ≈ 210.1 MB (2026-11-06 13:37:18), fichier unique intégrant PySide6 / QtWebEngine ainsi que toutes les dépendances `translations`, `data` et `resources`
- Vérification du lancement : exécution directe de `dist/MikanCL.exe`, `dist/data/logs/launcher.log` a écrit « Lanceur prêt » à 13:38:14, le processus est resté en cours d'exécution, puis le processus de test a été terminé après vérification

## Conseils de mise à niveau

- Cette version corrige et ajoute des éléments sur la base de v4.9.2, avec le numéro de version mis à jour à 4.9.3 ; il suffit de remplacer l'ancien fichier par le nouveau `MikanCL.exe`, la configuration, les instances et l'historique de téléchargement sous `data/` étant tous conservés
- Le mode « Installateur officiel » lance l'assistant d'installation du système et peut demander des droits administrateur ; si l'ordinateur de l'entreprise interdit l'installation, utilisez plutôt le ZIP portable

---

Date de publication : 2026-11-05

# MikanCL v4.9.2 — Notes de version

Date de publication : 2026-11-05

## Ajouts

- **Onglet « Accélérateur de téléchargement »** : la barre latérale ajoute une page indépendante où il suffit de coller n'importe quel lien direct de téléchargement pour le télécharger avec le téléchargeur segmenté à haut nombre de threads du lanceur ; prise en charge du collage de plusieurs liens ou d'un bloc de texte entier (extraction automatique des liens http/https, déduplication, reconnaissance de la ponctuation finale), du choix séparé du répertoire de sauvegarde, et jusqu'à 328 threads par tâche. Les tâches sont uniformément enregistrées dans le centre de téléchargement, avec pause / reprise / annulation / nouvelle tentative en cas d'échec ; les fragments déjà téléchargés sont conservés et repris ; les fichiers de même nom reçoivent automatiquement un numéro d'ordre, sans écrasement ni concurrence avec une tâche en cours sur le même fichier
- **Budget partagé de 328 threads pour tous les téléchargements** : `net.py` ajoute un `BoundedSemaphore(328)` global, acquis uniquement au niveau des threads feuilles qui lisent réellement le réseau ; l'installation de versions, le téléchargement Java, les fichiers de contenu, l'accélérateur de téléchargement et le téléchargement par blocs de l'édition Bedrock partagent tous ce budget. Au passage, la limite stricte de 16 segments par fichier est levée : le découpage se fait désormais selon `taille du fichier / 1 MB`, la concurrence réelle étant bornée par le budget global et le nombre de threads des paramètres
- **Préchargement JVM (expérimental, désactivé par défaut)** : la page Paramètres → Général ajoute un interrupteur et une liste déroulante « Java préchargé » (par défaut, suivi automatique du Java sélectionné au lancement). Une fois activé, chaque lancement du lanceur exécute en arrière-plan `-Xshare:auto -XX:+UseSerialGC -version` avec le Java choisi, afin de préchauffer les classes de base et les bibliothèques natives dans le cache système ; tout se passe en thread d'arrière-plan, un échec n'écrit que dans les journaux sans affecter l'interface ni le processus de lancement, et la fermeture de la fenêtre attend la fin du thread de préchauffage
- **Optimisation de la vitesse de démarrage** : `scroll_page()` ne définit plus de `setStyleSheet` inline séparé pour chaque page (le fond est désormais dessiné uniformément par les règles globales de `theme.py`, avec une nouvelle règle `QScrollArea#SidebarScroll` conservant l'aspect de la barre latérale) ; `MainWindow._apply_appearance()` ajoute un cache d'état (image de fond, verre dépoli) et une comparaison de signature de feuille de style de fenêtre, en sautant totalement `setStyleSheet` et les réglages par ScrollArea quand l'état n'a pas changé. Mesure hors écran : construction de la fenêtre principale passée d'environ 5.7 secondes à environ 3.5 secondes

## Correctifs

- **Détection des chemins Java plus complète** : en plus du registre, de `JAVA_HOME`, des répertoires de distributions courantes et du répertoire autogéré du lanceur, ajout de `shutil.which`, de toutes les lignes de sortie de `where java` / `where javaw` sous Windows, ainsi que du balayage répertoire par répertoire du `PATH` (déduplication uniforme par chemin normalisé en minuscules, seuls les fichiers réellement existants étant conservés) ; dès que `java` s'exécute en ligne de commande, le lanceur peut le détecter
- **Compatibilité des chemins de préchauffage JVM** : lorsque la préchargement sélectionne la racine d'installation de Java, `bin\javaw.exe` est localisé automatiquement, avec repli sur `bin\java.exe` s'il manque ; la comparaison avec le Java choisi par l'utilisateur se fait par chemin normalisé, une différence de casse ou de barre oblique n'entraînant plus de repli vers une autre version
- **Cycle de vie des QThread** : les objets de thread d'analyse Java et de préchargement JVM sont désormais libérés après le signal `finished`, évitant de détruire dans le slot `done` un `QThread` encore en cours d'exécution

## Build et vérification

- Artefact : `dist/MikanCL.exe`, 221,202,421 octets (2026-11-05 13:46:01), fichier unique intégrant PySide6 / QtWebEngine ainsi que toutes les dépendances `translations`, `data` et `resources`
- Vérification du lancement : 25 secondes après le démarrage de l'exe, le processus était toujours en cours, `data/logs/launcher.log` a écrit « Lanceur prêt », sans plantage
- Vérification de compilation : `python -m compileall mc_launcher` passe intégralement
- Vérification de fumée : 27 vérifications hors écran toutes réussies — limite de 328 et bridage du nombre de threads, lecture/écriture des nouveaux champs de configuration, entrées de détection `where`/PATH, refus du préchargement pour un chemin vide ou inexistant, cohérence entre pages de la fenêtre principale et navigation (19 pages dans la configuration courante), extraction / déduplication / nombre de threads par défaut des URL de la page de l'accélérateur de téléchargement, taille sur disque et nettoyage des fichiers temporaires d'un vrai téléchargement HTTP en lien direct
- Vérification de téléchargement : un lien direct local de 3 MB soumis via la page de l'accélérateur de téléchargement, avec repli correct en flux unique et vérification complète lorsque le serveur ne prend pas en charge Range, `.part` / `.merge` tous nettoyés
- Vérification des segments : deux fichiers locaux de 8 MB téléchargés en segments concurrents sur un serveur Range local (128 threads/tâche), vérification entièrement réussie ; pause de 1 seconde puis reprise du préchauffage, et `Cancelled` levé correctement après annulation, le budget global étant activement cédé pendant la pause, sans débordement du compteur `BoundedSemaphore`
- Connu : le script hors écran (`QT_QPA_PLATFORM=offscreen`) déclenche un plantage à la sortie de QtWebEngine lors de la destruction de la fenêtre principale contenant WebEngine avant `os._exit` (code de sortie non nul, `0xC0000005` / `0xC0000409`), affectant uniquement le processus de test hors écran ; l'exécution normale passe par le chemin « saut de la destruction Qt/Python en phase de sortie » de `main.py` et n'est pas affectée

## Conseils de mise à niveau

- Cette version ajoute des fonctionnalités sur la base de v4.9.1, avec le numéro de version mis à jour à 4.9.2 ; il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe
- Le préchargement JVM est une fonction expérimentale, désactivé par défaut ; en cas de ralentissement du démarrage ou d'anomalie de chemin Java, il peut être désactivé dans la page de paramètres

---

Date de publication : 2026-11-04

# MikanCL v4.9.1 — Notes de version

## Ajouts

- **Nouvelles sources miroirs nationales dans le centre Java** : ajout de « Miroir Tsinghua TUNA (Temurin) » et « Miroir Huawei Cloud OpenJDK », portant le total des distributions à 12 ; les sources marquées « miroir national » offrent une vitesse nettement meilleure en connexion directe depuis le pays, le miroir Tsinghua fournissant JRE / JDK et Huawei Cloud un JDK complet
- **Téléchargement segmenté multithread pour tous les fichiers volumineux** : `Http.download()` s'applique désormais à toutes les ressources — lorsque le fichier fait ≥ 4 MB et que le serveur prend en charge Range, il est automatiquement découpé en 8 segments téléchargés en concurrence puis fusionnés sur disque, avec prise en charge de la pause, de l'annulation et de la reprise de téléchargement par segment ; si le serveur ne prend pas en charge la segmentation, repli automatique en flux unique, sans affecter la logique existante de changement de source, de vérification et de nouvelle tentative. Le téléchargement des installateurs Java active systématiquement la segmentation
- **Ajout manuel d'un chemin Java** : Paramètres → Général → Runtime Java ajoute « Ajouter manuellement… », permettant de choisir `javaw.exe` / `java.exe` ou de saisir directement le répertoire d'installation ; le chemin est écrit dans la configuration pour être conservé à long terme et reste reconnu après redémarrage
- **Import de configuration depuis PCL2 / HMCL** : Paramètres → Jeu ajoute « Importer depuis PCL / HMCL… », qui analyse automatiquement les versions après sélection du répertoire de configuration de l'autre lanceur (racine du lanceur ou `.minecraft` directement) ; seules les versions absentes de ce lanceur sont importées, et une fois cochées elles sont enregistrées comme instances pointant directement vers le répertoire de jeu d'origine, les mods, sauvegardes de monde et packs de ressources n'ayant pas besoin d'être déplacés
- **Import des paramètres de jeu** : lecture de `Setup.ini` / `PCL.ini` de PCL et de `hmclversion.cfg` / `.hmcl.json` de HMCL, avec correspondance de l'isolation de version, de la mémoire maximale, des arguments JVM, du titre de fenêtre et du chemin Java par défaut vers les paramètres de version de ce lanceur ; une case permet de choisir si les paramètres globaux sont également importés
- **Nouvelle barre latérale « Modpack » dans les paramètres de version** : réutilisant le format de paquet `.mikan`, elle permet d'exporter la version courante en modpack ou d'injecter directement les fichiers d'un modpack `.mikan` / CurseForge / Modrinth dans l'instance courante — reconnaissance des préfixes `overrides/`, `client-overrides/` et des répertoires `mods` / `config` / `resourcepacks` / `shaderpacks` placés directement à la racine (écrits selon les règles d'isolation de version) ; l'import s'exécute en thread d'arrière-plan avec affichage de la progression, un décompte et une demande de confirmation précèdent le recouvrement de fichiers de même nom, et aucune nouvelle instance n'est créée ; le bouton d'export de la page « Gestion des versions » est déplacé ici, avec conservation de l'avertissement de migration

## Correctifs

- **Détection Java intermittente** : la cause racine est que chaque rafraîchissement remplaçait entièrement la liste par le résultat d'une analyse et que l'analyse ne prenait que les 60 premiers éléments par répertoire ; un changement de contenu du répertoire pouvait donc faire manquer un Java ; désormais, énumération complète + fusion avec la liste existante par chemin, et persistance des résultats de détection dans `java_known_paths`, les chemins manuels étant enregistrés dans `java_manual_paths` ; le rafraîchissement sonde d'abord les chemins historiques, de sorte que « présent cette fois, absent la fois suivante » ne se produit plus
- Extension de la portée de l'analyse Java : ajout des répertoires de distributions GraalVM, SapMachine, Dragonwell, Semeru, AdoptOpenJDK, Tencent, Alibaba, ainsi que de `LOCALAPPDATA\Programs\Java`, `~/.gradle/jdks` et `~/.jdks`
- Les Java désinstallés / dont le chemin est invalide sont automatiquement retirés de la liste au rafraîchissement, évitant la persistance d'entrées invalides
- **Ajout d'un repli pour les sources miroirs nationales** : les miroirs Tsinghua TUNA et Huawei Cloud récupèrent tous deux une liste de répertoires HTML, plus sensibles qu'une API à une refonte du répertoire ou à un 503 temporaire ; tous deux sont désormais complétés par le lien stable latest officiel d'Adoptium comme filet de sécurité, et une source indisponible n'affiche plus directement « Échec de récupération »
- **L'analyse Java n'est plus tronquée** : la limite de sous-répertoires candidats par racine d'installation passe de 400 à 2000, et celle des sous-sous-répertoires de 40 à 200 ; lorsque l'utilisateur pointe `JAVA_HOME` vers un répertoire de JDK accumulé depuis longtemps (comme `~/.gradle/jdks`), aucune détection n'est manquée
- **Chemin normalisé pour le jugement d'idempotence à l'import d'instances** : la comparaison applique d'abord `resolve()` pour éliminer `..` et la barre oblique finale, puis unifie la casse ; un même répertoire écrit `E:\1.20.1-Fabric`, `E:\1.20.1-Fabric\` ou avec une casse différente ne crée plus d'instance en double
- **Nettoyage des résidus de téléchargement segmenté** : avant de commencer un téléchargement segmenté, le fichier de fusion `.merge` laissé par une interruption précédente est supprimé, évitant l'occupation d'espace disque après un arrêt forcé du processus ; le paramètre `size` de `_segmented_download()` accepte explicitement `None`, et la documentation de `Http.download()` précise que `on_bytes` a une sémantique incrémentale et qu'à la reprise, la quantité déjà téléchargée est d'abord ajoutée
- Réorganisation de la robustesse de l'import de modpack et de la détection de conflits de Mods : la détection de conflits passe à un import au niveau du module, sans plus de branche `ImportError` silencieusement ignorée ; les deux replis ligne par ligne de `_read_ini()` sont fusionnés en `_parse_flat()` ; les mots-clés de mémoire passent de `ram/memory/mem` à `ram/memory`, évitant les fausses correspondances ; la barre latérale passe à `(clé, libellé)` avec mappage des pages par clé, l'insertion d'une nouvelle page ne décalant plus l'ensemble ; après un téléchargement Java, le tableau n'est plus reconstruit inutilement

## Build et vérification

- Artefact : `dist/MikanCL.exe` (fichier unique, 220,325,593 octets ≈ 210.1 MB, intégrant PySide6 / QtWebEngine ainsi que toutes les dépendances `translations`, `data` et `resources`)
- Heure de build : 2026-11-04 20:57:55 ; le journal d'empaquetage indique `Build complete`
- Vérification du lancement : exécution directe de `dist/MikanCL.exe`, `dist/data/logs/launcher.log` a écrit « Lanceur prêt » à 20:58:41, le processus est resté en cours d'exécution, puis le processus de test a été terminé après vérification
- Vérification de compilation : `python -m compileall mc_launcher` passe intégralement, test de fumée hors écran sans erreur
- Vérification fonctionnelle : le répertoire de test PCL `E:\1.20.1-Fabric 0.19.5-OptiFine_I6` a été analysé et a identifié 1.16.5 (PCL / isolation de version / description) ; après import, l'instance et les paramètres de version sont correctement écrits, la configuration ayant été restaurée à la fin du test
- Vérification de téléchargement : un JRE de 49 MB téléchargé depuis le miroir Tsinghua TUNA en 8 segments concurrents s'est terminé en 5.6 secondes, les fichiers temporaires de segmentation étant tous nettoyés
- Fumée de l'interface : création hors écran du centre Java (12 distributions), de la page de paramètres, de la page de paramètres de version (7 onglets de barre latérale) et de la boîte de dialogue d'import, toutes construites correctement
- Vérification des correctifs de revue : `tuna` / `huawei` figurent bien dans `_FALLBACK_FETCHERS` ; un même répertoire écrit avec une barre oblique finale, une casse différente ou contenant `..` donne le même identifiant d'instance ; `_parse_flat()` analyse `Ram:8192` de PCL et `maxMemory=4096` de HMCL, et des clés comme `remember` ne sont plus prises pour de la mémoire ; le `.mikan` synthétique (avec `overrides/`, `client-overrides/`, `mods/` à la racine) est reconnu comme 3 entrées, toutes écrites sur disque, avec un décompte de recouvrement correct, la progression de `ImportPackWorker` se terminant normalement de 0→1 ; les 7 éléments de la barre latérale correspondent au mappage des clés de page, et `_select_nav()` se positionne correctement ; `_segmented_download(size=None)` ne lève plus `TypeError`

## Conseils de mise à niveau

- Cette version est une révision de v4.9.0, avec le numéro de version mis à jour à 4.9.1 ; il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe
- Les instances PCL / HMCL déjà enregistrées via l'import de module n'ont pas besoin d'être réimportées ; après mise à niveau, un même répertoire n'est plus considéré comme une nouvelle instance

---

# MikanCL v4.8.2 — Notes de version

Date de publication : 2026-11-03

## Correctifs

- **Échec du chargement du pack de skins** : retour au mode d'écriture et de chargement du pack de skins qui fonctionnait dans l'ancienne version — le pack de ressources écrit simultanément les deux ensembles de chemins `textures/entity/steve.png`, `alex.png` et `textures/entity/player/wide/steve.png`, `slim/alex.png`, au lieu d'un seul chemin selon la version ; la limite supérieure de `supported_formats` dans `pack.mcmeta` est ramenée de « pack_format courant » à 1–99, les différences de format entre versions voisines n'étant plus jugées incompatibles ; 1.21.9+ / 26.x continuent d'utiliser `min_format` / `max_format`, l'adaptation multi-versions restant inchangée
- **Le pack de partage ne pouvait pas être chargé directement** : le `.zip` exporté n'imbrique plus le pack de ressources dans un sous-répertoire `resourcepack/`, mais place `pack.mcmeta` / `pack.txt` et les textures directement à la racine du paquet, le fichier lui-même pouvant ainsi être placé dans `resourcepacks` (ou `texturepacks` pour 1.5.2 et antérieur) pour être chargé ; l'import par le lanceur lit toujours le `skin.png` à la racine et régénère un pack adapté selon la version sélectionnée sur la machine
- **Cause racine de l'inefficacité du pack de skins** : l'ancien code n'écrivait qu'un seul chemin de texture selon le modèle de bras (test réel : le pack `MikanCL-luohaocheng-皮肤包.zip` généré par l'ancienne version ne contenait que `assets/minecraft/textures/entity/alex.png`, avec `pack_format=1` et `supported_formats` 1–1) ; lorsque le joueur utilisait réellement le modèle Steve (wide), ce chemin n'était pas chargé, si bien que le pack de ressources affichait « adapté » alors que le jeu conservait le skin par défaut ; l'ancien pack, parce qu'il écrivait simultanément les quatre chemins `steve.png` et `alex.png`, fonctionnait encore après activation forcée même s'il affichait une incompatibilité en rouge. L'écriture de l'ancien pack est désormais restaurée, les quatre chemins étant écrits simultanément, indépendamment du modèle de bras
- **Réinstallation nécessaire après mise à niveau** : les `MikanCL-*.zip` déjà écrits dans les répertoires de jeu par l'ancien code ne sont pas réécrits automatiquement ; utilisez « Ajouter et recouvrir l'ancien pack de skins en un clic » de 4.8.2, ou relancez une installation, pour générer un nouveau pack contenant les quatre chemins de texture

## Ajouts

- **Onglet « Complétion des dépendances »** : la barre latérale ajoute une page indépendante listant de façon centralisée toutes les dépendances tierces non intégrables en raison de restrictions de licence, de taille ou de canal de distribution officiel — multijoueur Terracotta (Terracotta 0.4.2), authlib-injector, runtime Java, chargeurs de Mods (Forge / Fabric / NeoForge / Quilt) et Forbric ; l'état d'installation, la version, la licence et le chemin sont affichés par catégorie ; les modules manquants téléchargeables directement affichent « Télécharger », ceux installés affichent « Localiser », et ceux nécessitant l'installateur officiel affichent « Aller à » vers la page correspondante
- **Entrée de téléchargement unifiée pour les modules tiers** : un clic sur « Télécharger » récupère depuis l'adresse de publication officielle de chaque module, la tâche étant enregistrée dans le centre de téléchargement et prenant en charge pause / annulation / nouvelle tentative en cas d'échec comme un téléchargement ordinaire
- **Clause de non-responsabilité pour les modules tiers** : le haut de la page des dépendances affiche en permanence une explication — ces modules ne sont fournis que comme entrées de téléchargement pour la commodité de l'utilisateur, sont maintenus indépendamment par leurs propres auteurs, et les problèmes rencontrés lors du téléchargement ou de l'utilisation sont à la charge de l'utilisateur, les auteurs de MikanCL n'en étant aucunement responsables
- **Vérification des dépendances manquantes du jeu** : après sélection d'une version installée, vérification en un clic du Java requis, du jar client, des bibliothèques de dépendances `libraries`, de l'index de ressources `assets` et de ses objets, de la configuration de journalisation log4j et du fichier de version ; le tableau de résultats indique point par point « manquant / complet » avec une explication précise
- **Complétion silencieuse avec demande de confirmation** : lorsque la vérification détecte des manques, une boîte de dialogue demande « Compléter automatiquement maintenant ? » ; après confirmation, l'exécution se fait silencieusement en arrière-plan — un Java manquant entraîne le téléchargement automatique du JRE Adoptium, les fichiers manquants passent par une complétion de version ne comblant que les lacunes, toutes les tâches apparaissent dans le centre de téléchargement et l'utilisation du lanceur n'est pas bloquée avant leur achèvement
- **Contrat utilisateur mis à niveau vers la v1.4** : ajout de l'article 11 « Modules tiers », précisant que les modules tiers n'ont aucune relation d'affiliation, d'autorisation, de parrainage ou de garantie avec MikanCL, que la fourniture d'entrées n'est qu'une commodité et que les risques associés sont à la charge de l'utilisateur ; synchronisé en 5 langues (chinois / anglais / russe / français / japonais)
- **Onglet « Pack de skins »** : la barre latérale ajoute une page indépendante générant un pack de skins partageable selon « joueur cible + modèle de bras + version de jeu » (`.zip`, contenant `pack.json`, `skin.png`, un pack de ressources adapté à la version et une notice), installable directement sur la machine locale ; prise en charge de l'import du pack de skins d'un autre utilisateur ou d'un PNG unique
- **Skin appliqué par joueur** : les textures de skin par défaut ne sont plus remplacées globalement ; le skin est écrit dans `CustomSkinLoader/LocalSkin/skins/<nom du joueur>.png` et le `loadlist` de `CustomSkinLoader.json` est fusionné (espace réservé `{USERNAME}`), de sorte que seul le joueur désigné affiche ce skin sur le serveur, les autres joueurs n'étant pas affectés
- **Adaptation du pack de skins à toutes les versions** : 1.0–1.5.2 génère un pack de textures `texturepacks` (`pack.txt` + `textures/entity/*.png`) ; 1.6.1–1.21.8 utilise le `pack_format` de `pack.mcmeta` (1 / 2 / 3 … 64 selon la version) avec `supported_formats` 1–99 ; 1.21.9+ et 26.x (y compris la bêta 26.4) passent à `min_format` / `max_format` ; les deux ensembles de chemins de texture joueur, anciens et nouveaux (`textures/entity/steve|alex.png` et `entity/player/wide|slim`), sont écrits simultanément, de sorte que toute version trouve le skin
- **Demande du modèle de bras** : avant d'importer un skin local, d'appliquer une œuvre de l'atelier de skins, d'importer ou d'exporter un pack de skins, Steve (classique) ou Alex (fin) est demandé ; le choix est enregistré dans `skin_model` du compte et réutilisé lors de l'empaquetage automatique et des imports de nouvelles versions
- **Empaquetage automatique avec la version** : à la fin du téléchargement-installation d'une nouvelle version, de l'import d'un modpack / pack d'installation directe ou de la restauration d'une instance, un pack de skins au format de cette version est généré automatiquement et écrit dans `CustomSkinLoader/LocalSkin`, sans nécessiter un nouveau lancement
- **Ajout en un clic avec recouvrement de l'ancien pack de skins** : la page du pack de skins ajoute un bouton qui nettoie d'abord tous les `MikanCL-*.zip` du répertoire principal et des répertoires d'isolation de version (y compris l'ancien `MikanCL-离线皮肤.zip`) ainsi que les entrées d'activation `file/MikanCL-*` de `options.txt`, avant d'écrire le skin courant ; l'installation ordinaire d'un nouveau pack nettoie également de façon automatique, évitant qu'un ancien pack résiduel ne fasse croire à l'application du nouveau skin
- **Arguments JVM intelligents** : la page Paramètres → Général ajoute un interrupteur (activé par défaut) qui ajoute automatiquement des arguments selon la version majeure de Java, la version de jeu et la taille du tas : 1.21 et antérieur utilise G1GC de style Aikar (proportion de la jeune génération, Region, IHOP, objectif de pause, etc.), `AlwaysPreTouch` n'étant activé qu'à partir de 4 GB de tas et les Region de 16 MB à partir de 12 GB ; 26.x (Java 25 requis officiellement) passe au ZGC générationnel (`-XX:+UseZGC`) ; les arguments sont ignorés automatiquement si un GC (y compris la forme négative `-XX:-UseG1GC`) ou un argument de même nom est déjà spécifié dans les arguments JVM supplémentaires ; Java 7 et antérieur ne reçoit que `MaxPermSize=256M` ; une mémoire allouée dépassant 60 % de la mémoire physique déclenche un avertissement sur le risque de pagination
- **Arguments de lancement compatibles par version** : 1.12.2 et antérieur ajoute automatiquement `-Xss1M` (MC-129374) et `-Djava.util.Arrays.useLegacyMergeSort=true` (MC-61156) ; les anciens Forge / modpacks à jar modifié reçoivent `-Dfml.ignoreInvalidMinecraftCertificates=true`, `-Dfml.ignorePatchDiscrepancies=true` ; une ancienne version associée à Java 9+ reçoit automatiquement les arguments d'ouverture de modules `--add-opens` ; Java 24+ reçoit `--enable-native-access=ALL-UNNAMED` ; macOS 1.13+ reçoit `-XstartOnFirstThread`. Ces arguments ne dépendent pas de l'interrupteur « JVM intelligente » et s'appliquent toujours
- **Correctif de l'identification des numéros de version** : `infer_java_major` renvoie Java 25 pour les versions 26.x / 26w.. (au lieu de 21 par erreur), Java 8 pour les versions anciennes (`a1.2.6` / `b1.7.3` / `c0.30` / `inf-` / `rd-` / `1.rv` / `2.0`) et les snapshots antérieurs à 1.14, `3d shareware v1.34` étant également classé en Java 8
- **Installation simultanée de 5 versions au maximum** : la page d'installation par téléchargement lève la restriction « une seule version installable à la fois » ; jusqu'à 5 versions peuvent être installées en même temps, avec progression, pause et annulation indépendantes par version ; la 6e version doit attendre une place libre

## Correctifs et optimisations

- **Correctif du plantage systématique à l'installation de modpack** : `ContentInstallWorker._emit()` n'acceptait que la progression et l'explication, mais recevait `stage / files_done / files_total`, levant `TypeError`, ce qui faisait échouer toutes les installations de modpack à l'étape de téléchargement du contenu ; la signature est désormais étendue et l'étape est intégrée au texte d'explication
- Si l'utilisateur change de chargeur pendant l'estimation asynchrone de l'occupation disque de la page de téléchargement, l'estimation ne fait plus revenir le choix en arrière à son achèvement, mais abandonne directement cette installation
- L'UUID hors ligne est uniformément fourni par `auth.offline_uuid()`, `launcher.py` ne maintenant plus une seconde implémentation
- Le thread d'écoute de la sortie du jeu reçoit désormais l'objet bus, et la fermeture du lanceur ne référence plus de page potentiellement détruite ; à la fermeture, le marqueur de vérification différée de l'édition Bedrock est nettoyé de façon synchronisée
- Lors d'un changement de langue, si le fichier de traduction `.qm` cible manque, le message « Fichier de traduction manquant, retour au chinois » s'affiche et le choix précédent est restauré, plutôt que d'enregistrer une langue qui reste le chinois après redémarrage
- Paramètres → Interrupteurs fonctionnels ajoute un interrupteur d'onglet « Complétion des dépendances » ; une fois désactivé, aucune page n'est créée et aucune tâche d'arrière-plan n'est lancée ; effet au redémarrage
- Les tâches de complétion des dépendances réutilisent la file et le mécanisme de nouvelle tentative du centre de téléchargement, et le marqueur d'annulation précédent est automatiquement effacé avant une nouvelle tentative, évitant « nouvelle tentative après annulation qui annule immédiatement à nouveau »
- L'analyse des dépendances traite défensivement les architectures CPU non prises en charge, les index de ressources manquants et les JSON de version corrompus ; l'échec d'une vérification de page n'affecte pas les autres fonctions du lanceur
- Une fois la complétion terminée, la liste Java et l'état des versions sont automatiquement rafraîchis, avec une invite permettant de revérifier ou de lancer directement
- Lors d'installations simultanées de plusieurs versions, les bibliothèques de dépendances / fichiers de ressources partagés peuvent être demandés simultanément par plusieurs threads : `Http.download()` verrouille désormais selon le chemin cible et revérifie si le fichier est déjà complet après obtention du verrou, évitant les conflits d'écriture `.part` et les téléchargements en double
- Le nombre de tâches simultanées par défaut du centre de téléchargement passe de 2 à 5, en cohérence avec la limite d'installation simultanée de la page, les autres tâches étant automatiquement mises en file d'attente

## Build et vérification

- Artefact : `dist/MikanCL.exe` (fichier unique, 221,115,875 octets ≈ 210.9 MB, intégrant PySide6 / QtWebEngine ainsi que toutes les dépendances `translations`, `data` et `resources`)
- Heure de build : 2026-11-03 21:59:47 ; le journal d'empaquetage indique `Build complete`
- Vérification du lancement : exécution directe de `dist/MikanCL.exe`, `data/logs/launcher.log` a écrit « Lanceur prêt » à 22:01:24, le titre de fenêtre s'affichant normalement, puis le processus de test a été terminé après vérification
- Test de fumée hors écran réussi : « Complétion des dépendances » apparaît dans la barre latérale, création de la page, 5 lignes dans le tableau des modules (Terracotta / authlib-injector / runtime Java / chargeurs de Mods / Forbric), les interrupteurs fonctionnels de la page de paramètres incluent `deps`, et le bouton « Aller au centre Java » émet correctement le signal de navigation
- Test d'analyse des dépendances réussi : un répertoire de version synthétique identifie correctement 5 catégories de manques (Java, Jar client, bibliothèques de dépendances, index de ressources, configuration de journalisation) ; une version inexistante renvoie `kind="version"`
- Tests de concurrence et de skin réussis : `DownloadManager.max_concurrent == 5`, la page de téléchargement exécute 5 tâches en parallèle et la 6e est bloquée par la limite, le bouton d'installation étant désactivé à la limite ; `import_offline_skin()` écrit correctement `CustomSkinLoader/LocalSkin/skins/<nom du joueur>.png`, fusionne le `loadlist` de `CustomSkinLoader.json` et génère le pack de ressources de la version correspondante ; si `resourcepacks` manque dans le répertoire de jeu, il est créé automatiquement au préalable
- Vérification réussie de l'adaptation du pack de skins aux versions (écriture de l'ancien pack) : 1.5.2 → `pack.txt` + `textures/entity/steve.png`, `alex.png` ; 1.8.9 → `pack_format=1` + `supported_formats` 1–99 ; 1.12.2 → `pack_format=3` ; 1.20.1 → `pack_format=15` ; 1.21.8 → `pack_format=64` ; 1.6.1+ contient toujours les deux ensembles de chemins `textures/entity/steve|alex.png` et `entity/player/wide|slim` ; 1.21.9 → `min_format=[69,0]` / `max_format=[999,0]` ; 26.4-snapshot → `min_format=[97,0]` / `max_format=[999,0]` ; le `.zip` exporté contient directement `pack.mcmeta` / `pack.txt` et les textures à la racine, et peut être chargé directement par le jeu ; lors d'installations répétées pour différents joueurs, les entrées `LocalSkin` ne sont pas dupliquées et les sources de skin existantes de l'utilisateur comme `MojangAPI` sont conservées
- Vérification réussie du recouvrement de l'ancien pack de skins : `purge_old_packs()` supprime les `MikanCL-*.zip` sous `resourcepacks` / `texturepacks` (en conservant les autres packs de ressources) et retire simultanément les entrées d'activation de `options.txt` ; le nettoyage est automatique avant l'installation d'un nouveau pack, ne laissant finalement qu'un seul pack de secours `MikanCL-*`
- Vérification réussie des arguments JVM intelligents : Java 8 / 17 / 21 génèrent respectivement 19–20 arguments ; un tas de 2 GB n'inclut pas `AlwaysPreTouch`, un tas de 8 GB l'inclut ; un tas de 16 GB utilise `G1HeapRegionSize=16M` ; les préréglages G1 sont ignorés lorsque l'utilisateur spécifie `-XX:+UseZGC` ou `-XX:-UseG1GC` ; `-XX:MaxGCPauseMillis=300` n'est pas recouvert ; Java 7 renvoie `-XX:MaxPermSize=256M` ; une version Java inconnue renvoie une liste vide
- Vérification réussie des arguments de compatibilité par version : 1.7.10 → `-Xss1M` + tri legacy ; 1.7.10-forge → ajout des deux arguments fml ; 1.12.2 + Java 17 → ajout de 7 `--add-opens` ; 1.21.8 + Java 21 → aucun argument de compatibilité ; 26.1 / 26w01a + Java 25 → `-XX:+UseZGC` sans G1GC ; Java 24+ ajoute `--enable-native-access=ALL-UNNAMED` à toutes les versions
- Vérification réussie de l'assemblage de la commande complète : `build_launch_plan()` génère `-Xmx/-Xms` → arguments de réglage → arguments de compatibilité de version → encodage / marque → `-Djava.library.path` / `-cp` → classe principale ; les combinaisons 1.12.2, 1.21.8 et 26.1 ont un ordre et un contenu corrects
- Vérification réussie de l'identification des versions anciennes / spéciales : `b1.7.3`, `a1.2.6`, `c0.30_01c`, `inf-20100618`, `rd-132211`, `1.rv-pre1`, `2.0`, `12w01a`, `17w43a` sont toutes jugées legacy ; `20w14infinite` / `25w14craftmine` / `3d shareware v1.34` sont classées en Java 8 sans ajout d'arguments d'ancienne version ; `26w01a` est jugée Java 25

## Documentation

- Les fonctionnalités complètes, l'implémentation technique et la description des interfaces sont dans [README.md](README.md)
- Le résumé des changements de cette version figure dans la section v4.9.1 en haut de ce fichier

## Conseils de mise à niveau

- Il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe
- La mise à niveau depuis v4.7.0 ne nécessite plus de reconfirmer le « Contrat utilisateur v1.4 » (la version du contrat n'a pas changé)
- Les modules tiers sont téléchargés à la demande ; ne pas les télécharger n'affecte pas les autres fonctions du lanceur ; veuillez vérifier vous-même la source, la version et la licence open source avant utilisation

---

# MikanCL v4.6.2 — Notes de version

Date de publication : 2026-10-31

## Ajouts

- **Vue 3D du skin à 360° en libre** : le modèle d'aperçu prend en charge la rotation par glisser à la souris (yaw horizontal + pitch vertical), permettant de le voir sous n'importe quel angle ; zoom à la molette, déplacement par glisser avec le bouton droit ; un bouton de réinitialisation ramène en un clic à la vue par défaut
- **Bascule entre mode pinceau / mode souris** : l'aperçu 3D de l'atelier de skins ajoute des boutons mutuellement exclusifs « Pinceau / Souris » — en mode pinceau, le clic gauche dessine et le clic droit efface ; en mode souris, le glisser fait tourner, le dessin et la consultation étant totalement séparés et ne dépendant plus de Shift
- **Contrôle du zoom** : l'aperçu 3D ajoute des boutons de zoom « ＋/－ » et un affichage en pourcentage, de 20 % à 800 %
- **Skin réel entièrement visible en 360° sur la page de compte** : l'aperçu de skin de la page de gestion des comptes prend également en charge la rotation 360° par glisser, le zoom à la molette et le déplacement, avec des boutons rotation à gauche / à droite / réinitialisation / zoom

## Correctifs et optimisations

- Correction de l'impossibilité de régler verticalement l'angle de vue lors du dessin 3D du skin (ajout de l'axe pitch)
- Le dessin 3D et le skin réel 3D passent tous deux à une vue complète en 360°, avec une logique d'interaction unifiée
- Les textes d'aide sont mis à jour pour expliquer le double mode pinceau / souris, synchronisés en 5 langues

## Conseils de mise à niveau

- Il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe

---

# MikanCL v4.6.1 — Notes de version

Date de publication : 2026-10-31

## Ajouts

- **Bascule entre bruit classique / nouvelle génération** : la page du terrain par graine ajoute une liste déroulante « Version du bruit » — classique (1.7–1.17, `ImprovedNoise` avec table de permutation de 256 entrées + table de gradients à 16 directions, 8 octaves cumulés avec persistence 0.5 / lacunarity 2) et nouvelle génération (1.18+, source aléatoire `Xoroshiro128++` + bruits climatiques de continentalité / érosion / singularité) ; les paramètres des deux modes sont les valeurs fixes de la vanilla, sans aucun réglage supplémentaire
- **Taille du terrain par graine sans limite supérieure** : la limite supérieure du champ de taille est supprimée (32 ~ 2147483647), avec 256×256 par défaut (plage de survie) ; plus la taille est grande, plus la génération est longue ; côté rendu, un sous-échantillonnage automatique selon la taille évite une explosion du nombre de sommets

## Correctifs et optimisations

- **Correctif du plantage de l'aperçu 3D du skin** : `_draw_texel` déballait un enregistrement de correspondance à 9 valeurs comme s'il en avait 7, levant `ValueError: too many values to unpack (expected 7, got 9)` ; le déballage se fait désormais à partir de `rec[2:]`
- **Correctif de l'inondation de messages `QBackingStore::endPaint() called with active painter`** : `paintEvent` est scindé en un wrapper + `_paint`, avec `try/finally` garantissant la fin du painter même en cas d'exception
- La carte des hauteurs du terrain passe à une normalisation en deux passes selon le min/max de l'image courante ; les modes classique et nouvelle génération couvrent tous deux le gradient complet de hauteur 0–255, sans plus de distorsion donnant une image entièrement océan ou plaine
- La page de graine supprime le curseur « Relief » et autres paramètres personnalisés, la génération suivant totalement les paramètres fixes de la vanilla
- L'article 9 du contrat utilisateur est mis à jour pour la formulation en double mode (5 langues)

## Conseils de mise à niveau

- Il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe

---

# MikanCL v4.6.0 — Notes de version

Date de publication : 2026-10-31

## Ajouts

- **Terrain rendu en blocs Minecraft** : le terrain 3D de la graine de monde n'utilise plus un maillage triangulaire lisse, mais un rendu en colonnes de voxels — une cellule, un bloc, sommet plat et faces en escalier visibles uniquement vers les voisins plus bas, niveau de la mer automatiquement aplati, faces latérales assombries selon l'orientation (0.60 en x / 0.78 en z), visuellement cohérent avec le relief de blocs en jeu
- **Barre de boutons d'interaction du terrain** : sous la vue 3D, ajout de boutons « Angle de vue ◀▶▲▼ / Zoom ＋－ / Déplacement ←→↑↓ / Réinitialiser la vue / Rotation automatique », permettant de contrôler entièrement l'angle sans souris ; la rotation par glisser, le zoom à la molette et le déplacement par clic droit sont conservés, avec ajout de la réinitialisation par double-clic
- **Peinture multi-couches du skin** : l'atelier de skins prend en charge jusqu'à 8 calques, avec une zone d'édition multicouche sous le canevas — cases à cocher pour la visibilité, clic pour changer de calque actif, création / suppression / déplacement vers le haut / vers le bas ; le calque de base ne peut pas être supprimé ; l'export PNG, l'enregistrement dans la bibliothèque et l'application au compte fusionnent automatiquement tous les calques visibles
- **Nouveaux outils de pinceau** : ajout de quatre outils ligne, rectangle, ellipse (aperçu pendant le glisser, validation au relâchement) et aérographe (points aléatoires selon la taille du pinceau), soit dix outils sur une ligne de barre d'outils ; en dessin 3D, les outils de forme se réduisent automatiquement à un pinceau d'un pixel
- **Boutons d'angle de vue 3D du skin** : la ligne d'angle de vue de l'aperçu 3D ajoute des boutons « Rotation à gauche / à droite / Réinitialiser la vue » (15° par clic), ne dépendant plus seulement du curseur et du glisser
- Tous les textes des nouvelles fonctionnalités sont intégrés aux fichiers de traduction en 5 langues (chinois / anglais / russe / français / japonais)

## Correctifs et optimisations

- **Renforcement du dessin de skin contre les plantages** : le passage d'outil / de calque / l'annulation-rétablissement / l'effacement / le chargement d'image interrompt automatiquement le trait et l'aperçu de forme en cours ; tous les appels `QPainter` sont protégés par try/finally ; le début / la fin de trait sont idempotents ; les coordonnées sont uniformément bridées aux limites, un test de stress de 30 cycles d'opérations mixtes ayant passé
- L'annulation / le rétablissement passent à un instantané complet des calques, la structure multicouche (nombre de calques, ordre, visibilité, calque actif) étant intégralement restaurée avec l'historique
- L'info-bulle 3D ajoute une garde contre les dépassements UV, évitant un plantage de prélèvement de couleur sous des angles extrêmes

## Conseils de mise à niveau

- Il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe

---

# MikanCL v4.5.0 — Notes de version

Date de publication : 2026-10-31

## Ajouts

- **Dessin 3D du skin** : à droite de l'aperçu 3D, ajout d'une liste déroulante « Calque » (base / second calque), d'un curseur « Angle de vue » et d'un interrupteur « Rotation automatique » ; après sélection de la tête / du corps / des bras gauche et droit / des jambes gauche et droite, le dessin se fait directement sur le modèle 3D, le clic gauche dessinant avec l'outil courant et le clic droit effaçant, Shift + glisser faisant tourner le modèle, la barre d'état affichant en temps réel la partie touchée, les coordonnées de texture et la valeur de couleur
- **Rendu du second calque (overlay)** : les UV du second calque du chapeau / veste / manches / jambes participent au rendu 3D avec le calque de base, superposés avec une extension de 0.6 pixel et en conservant la semi-transparence ; les pixels transparents ne sont pas recouverts par le second calque
- Le dessin 3D réutilise tous les outils du canevas (pinceau / gomme / remplissage / pipette / éclaircir / assombrir, taille de pinceau, symétrie miroir), un trait ne poussant qu'un seul instantané d'annulation, avec synchronisation bidirectionnelle en temps réel avec le canevas 2D
- Les deux panneaux de calque prennent en charge le miroir : dans un même élément, la symétrie horizontale se fait selon le rectangle du calque de base ou du second calque où se trouvent réellement les pixels
- **Bruit du terrain identique à la vanilla** : `TerrainGen.java` passe au bruit de gradient de Perlin identique à Minecraft — `ImprovedNoise` (offset `Random(seed)` par trois `nextDouble()*256`, table de permutation de 256 entrées, table de gradients à 16 directions, interpolation cubique) + cumul multi-octaves (persistence 0.5 / lacunarity 2) ; sans biomes, splines de terrain ni fonctions de densité, il s'agit d'une représentation non officielle du terrain
- Le numéro de version des sources du terrain est mis à niveau (`SOURCE_VERSION=2`), l'ancien `TerrainGen.class` devenant automatiquement invalide et recompilé
- Le contrat utilisateur passe à la **v1.3** : l'article 8 complète le dessin 3D et l'édition à deux calques, l'article 9 décrit désormais exactement « algorithme de bruit et paramètres identiques à Minecraft, sans biomes ni splines de terrain », les 5 langues étant mises à jour de façon synchronisée

## Correctifs et optimisations

- Correction du problème où l'alpha des pixels restait à 255 après un effacement au clic droit sur le canevas 2D : l'effacement passe à `CompositionMode_Clear`, l'effacement au clic droit en 3D étant également corrigé
- Le rendu isométrique de l'aperçu 3D complète les six faces (y compris l'arrière et le dessous), l'algorithme du peintre triant par profondeur et le second calque étant toujours dessiné après le calque de base de même profondeur
- Le prélèvement 3D est résolu selon une liste de correspondances en ordre inverse, permettant de toucher avec précision les six parties après une rotation sous n'importe quel angle
- Le texte explicatif de la page de graine devient « algorithme et paramètres de bruit de Perlin identiques à Minecraft », en précisant l'absence de biomes et de splines de terrain

## Conseils de mise à niveau

- Il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe
- Le premier lancement de 4.5.0 demande de confirmer le « Contrat utilisateur v1.3 » mis à jour

---

# MikanCL v4.4.1 — Notes de version

Date de publication : 2026-10-30

## Ajouts

- **Atelier de skins** : éditeur de skin pixel 64×64 intégré, prenant en charge six outils pinceau / gomme / remplissage / pipette / éclaircir / assombrir, la taille de pinceau, la symétrie miroir horizontale, l'annulation / le rétablissement (40 étapes maximum, Ctrl+Z / Ctrl+Y), un zoom 4×~8× et un interrupteur de grille, avec mise en évidence des zones UV du calque de base et du second calque par partie (tête, corps, membres), affichage en temps réel des coordonnées du curseur et de la valeur de couleur ; aperçu 3D en temps réel des modèles Steve / Alex ; ajout d'une bibliothèque locale multi-skins (`data/skins`) pour enregistrer / charger / appliquer / supprimer plusieurs skins, exporter en PNG ou appliquer en un clic au compte courant
- **Graine de monde et aperçu du terrain** : après saisie d'une graine (numérique ou texte libre), le lanceur appelle le runtime Java local pour exécuter le `TerrainGen.java` intégré (bruit fBm de Perlin, implémentation non officielle de Minecraft, compilation `javac` en cache prioritaire, démarrage en fichier source unique Java 11+ en l'absence de compilateur) afin de générer une carte des hauteurs en thread d'arrière-plan, puis rend en WebGL via un `QWebEngineView` intégré le terrain 3D autour du point d'apparition (rotation par glisser, zoom à la molette, déplacement par clic droit), avec réglage de la taille et du relief et export de la carte des hauteurs en PNG ; le calcul du terrain n'est plus assuré par Python, évitant un plantage du processus principal
- **Animation de changement de page** : lors du changement d'onglet, la nouvelle page apparaît en fondu (environ 180ms, accélération OutCubic), désactivable dans « Paramètres → Apparence » pour réduire la charge GPU
- **Fond en verre dépoli** : sous Windows, activation d'un fond flou acrylique via `SetWindowCompositionAttribute` de DWM, sans lancer de processus supplémentaire ni accès réseau ; activable dans « Paramètres → Apparence », les systèmes non pris en charge revenant automatiquement à un fond sombre semi-transparent
- Le contrat utilisateur passe à la **v1.2**, avec ajout de trois clauses véridiques : atelier de skins et skin hors ligne, graine de monde et aperçu du terrain, effets d'interface et verre dépoli (mise à jour synchronisée en 5 langues)

## Correctifs et optimisations

- **Téléchargement de l'édition Bedrock passé au téléchargement par navigateur** : plus de dépendance à l'analyse de liens directs mis en cache hors ligne ; les entrées de version ouvrent désormais en un clic les pages MCAPPX / Microsoft Store dans le navigateur intégré (noyau Edge WebView2), et un clic sur le bouton de téléchargement de la page fait télécharger Edge sur la machine ; le lanceur surveille le répertoire de téléchargement et les nouveaux `.appx / .msix / .appxbundle / .msixbundle` téléchargés sont automatiquement archivés dans `data/bedrock/`, permettant ensuite une « Installation locale » directe
- Paramètres → Apparence ajoute une carte « Effets d'interface » gérant de façon centralisée l'animation de changement de page et l'interrupteur de verre dépoli
- Paramètres → Interrupteurs fonctionnels ajoute deux interrupteurs d'onglets « Atelier de skins » et « Graine de monde » (effet après redémarrage)
- La navigation de la fenêtre principale retrouve le numéro de page par la clé de page, une nouvelle page ne nécessitant plus de synchroniser un mappage numérique
- L'atelier de skins et la page du terrain par graine libèrent activement les threads d'arrière-plan et les ressources de rendu web à la fermeture, évitant tout processus résiduel à la sortie

## Conseils de mise à niveau

- Il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe
- Le premier lancement de 4.4.1 demande de confirmer le « Contrat utilisateur v1.2 » mis à jour

---

# MikanCL v4.4.0 — Notes de version

Date de publication : 2026-10-30

## Ajouts

- **Contrat utilisateur au premier lancement** : si la version courante du contrat n'a pas été acceptée, une boîte de confirmation s'affiche en premier au lancement ; les 7 articles au total (déclaration de non-officialité / comptes et connexion / contenu et téléchargement / données de jeu et risques d'exécution / requêtes réseau et confidentialité / exonération et limitation de responsabilité / modification et résiliation du contrat) sont présentés côte à côte sous forme d'onglets, le bouton « Accepter et continuer » étant inactif tant que « J'ai lu et j'accepte » n'est pas coché ; le choix « Refuser et quitter » ferme directement le programme sans entrer dans l'interface principale
- Le contrat intègre 5 langues (chinois, anglais, russe, français, japonais), avec bascule automatique selon la langue de l'interface
- Après acceptation, la version du contrat et l'heure d'acceptation sont écrites dans `data/config.json`, et l'utilisateur n'est plus sollicité ensuite ; une mise à niveau de version du contrat redemande confirmation
- Paramètres → À propos ajoute une carte « Contrat utilisateur » : consultation à tout moment du texte intégral et possibilité de désactiver l'interrupteur « Afficher la confirmation du contrat utilisateur au démarrage »

## Correctifs et optimisations

- Téléchargement de l'édition Bedrock : les octets résiduels de la reprise segmentée sont automatiquement tronqués avant la fusion, plus de faux message « taille de fichier incompatible » ; la requête du manifeste de la boutique peut être annulée, la fermeture du programme n'étant plus retenue par des nouvelles tentatives ; la colonne « Fichiers restants » du centre de téléchargement affiche désormais les segments terminés / le total des segments
- Détection de l'édition Bedrock déjà installée : passage à une correspondance par préfixe de version majeure ; les entrées de répertoire MCAPPX (par exemple 1.8.1 face au système 1.8.102.0) peuvent être correctement marquées « installées »
- Installation de l'édition Bedrock : le délai de grâce après le marqueur de succès PowerShell est continuellement rafraîchi selon la nouvelle sortie, les journaux longs n'étant plus tués à tort
- Forbric : en cas d'échec de l'interface de publication GitHub ou d'absence d'asset, repli automatique vers le lien direct de la dernière publication, sans plus dépendre d'un seul point de l'API du dépôt tiers
- Navigateur intégré (WebView2) : simplification des requêtes d'interface COM, unification des constantes IID, réduction des risques de compatibilité de pointeurs
- Navigation de la barre latérale : passage à une recherche par clé de page, une nouvelle page ne nécessitant plus de synchroniser un mappage manuel des numéros de page, éliminant les décalages de navigation

## Conseils de mise à niveau

- Il suffit de télécharger le nouveau `MikanCL.exe` et de remplacer l'ancien fichier, la configuration et les données restant sous `data/` dans le même répertoire que l'exe
- Le premier lancement de 4.4.0 demande de lire et d'accepter le « Contrat utilisateur » ; en cas de refus, l'entrée dans l'interface principale est impossible

