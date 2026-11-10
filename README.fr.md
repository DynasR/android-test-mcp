# android-test-mcp — en bref

Un serveur [MCP](https://modelcontextprotocol.io) qui permet à un agent IA de
piloter des émulateurs Android pour tester une app : l'installer, la lancer,
regarder l'écran, taper par libellé, lancer les tests d'intégration Flutter.
Sans danger.

*La documentation complète est en anglais : [README.md](README.md). Ce
résumé ne la remplace pas.*

**Le problème.** `adb` agit sur tout ce qui est branché, c'est un shell, et il
ne dit jamais qu'il a raté : un `input tap` dans le vide « réussit », un
lancement d'app absente échoue en silence et la capture suivante montre
l'écran d'avant.

**La réponse : quatre verrous indépendants**, chacun testé seul, comme si les
autres étaient cassés.

1. **Émulateurs seulement.** Le numéro de série doit avoir la forme
   `emulator-NNNN` *et* l'appareil doit se déclarer émulateur. Un téléphone
   réel n'est accepté que nommé au démarrage (`--allow-device`).
2. **Verbes fixes, arguments validés.** Sept outils, aucun shell, ni
   désinstallation ni effacement de données. Paquets et projets en liste
   blanche ; un chemin de test ne sort pas de son projet ; un APK doit
   déclarer dans son manifeste le paquet sous lequel on l'installe.
3. **Un seul travail lourd à la fois.** Installation et tests Flutter prennent
   un verrou de fichier du système, partagé par toutes les instances de la
   machine. Un second appel est refusé, avec le nom de celui qui tient le
   verrou.
4. **Des taps qui parlent.** L'agent nomme un libellé, jamais des coordonnées.
   Absent : erreur. Plusieurs correspondances : erreur qui liste les
   candidats, rien n'est tapé. Après le tap, la réponse dit si l'écran a
   changé et si le clavier est levé.

**La preuve.** `pytest` vérifie chaque verrou sans appareil (un faux adb rend
des sorties à la forme des vraies) ; `python tools/mutation_check.py` casse
chaque protection exprès et exige qu'un test passe au rouge.

**Essai réel (10/11/2026, émulateur tablette Android 16 x86_64).**
Installation, lancement, lecture des libellés Flutter, capture et tap avec
changement d'écran ont fonctionné ; les taps ambigus ou absents et un paquet
hors liste ont été refusés ; un APK arm64 seul a été refusé au lancement, et
le serveur dit désormais pourquoi (plantage, ABI absente). Pas encore essayés
en réel : `run_flutter_test` et un téléphone physique.

**Depuis :** `type_text` (ASCII limité à un jeu de caractères sûr, car `adb
shell` fait relire le texte par le shell de l'appareil), `set_airplane_mode`
(vérifié par le réglage de l'appareil) et `restart_app` (arrêt forcé puis
même chemin que le lancement), essayés en réel le soir même sur l'émulateur :
saisie vérifiée dans un champ Flutter (y compris en 3 morceaux), `;` et `é`
refusés avant toute frappe, mode avion basculé et confirmé, deux applis
relancées.

**Les limites.** Ni défilement, ni touche retour pour l'instant.
