// Engine-independent squad policy. Orders can later come from a commander UI.
#ifndef BOT_SQUAD_H
#define BOT_SQUAD_H

namespace botsquad
{
    enum Strategy { BALANCED, ATTACK, DEFEND };
    enum Role { ASSAULT, GUARD };
    enum CTFTask { NO_FLAG_TASK, STEAL_FLAG, RETURN_FLAG, ESCORT_FLAG, RECOVER_FLAG, INTERCEPT_FLAG };
    enum Transition { WAIT, ADVANCE, REGROUP, SOLO };

    inline int guards(int count, Strategy strategy)
    {
        if(strategy == DEFEND) return count;
        if(strategy == ATTACK) return 0;
        // Keep a pair available to leapfrog in a human + three bots squad.
        return count > 2 ? count / 2 : 0;
    }

    inline Transition transition(int elapsed, int movers, int supporters,
                                 bool arrived, bool supportready)
    {
        if(!movers || !supporters) return SOLO;
        if(elapsed >= 1200 && arrived && supportready) return ADVANCE;
        // A timeout regroups at actual positions; it never counts as arrival.
        if(elapsed >= 12000) return REGROUP;
        return WAIT;
    }
}

#endif
