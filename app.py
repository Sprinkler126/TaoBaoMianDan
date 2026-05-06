import itertools
from typing import Optional

import pandas as pd
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

EXCEL_FILE = "data.xlsx"

MAX_SOLUTIONS = 10


def load_data_from_excel(filepath: str) -> dict:
    try:
        df = pd.read_excel(filepath, engine='openpyxl')
    except Exception as e:
        print(f"读取Excel失败: {e}")
        return {}
    data = {}
    for col in df.columns:
        name = str(col)
        nums = []
        for x in df[col].dropna().tolist():
            try:
                nums.append(int(x))
            except (ValueError, TypeError):
                pass
        if nums:
            # 确保从大到小排序，并去重
            data[name] = sorted(set(nums), reverse=True)
    return data


def _dfs_amounts(num_lists, target, idx, current_combo, results, max_results):
    """
    在多个从大到小排序的数字列表中，DFS搜索总和等于target的组合。
    num_lists: [ [数字列表1], [数字列表2], ... ] 每个列表对应一个人
    idx: 当前处理第几个人
    current_combo: 当前已选的金额列表
    results: 收集结果
    max_results: 最多收集几个
    
    核心剪枝：
    - 每个列表从大到小排序，当前值如果加上后续所有人的最大值仍不够 → 剪（下限剪枝）
    - 当前值如果加上后续所有人的最小值已超过 → 剪（上限剪枝）
    """
    if len(results) >= max_results:
        return

    if idx == len(num_lists):
        if target == 0:
            results.append(tuple(current_combo))
        return

    remaining_count = len(num_lists) - idx - 1  # 后面还有几个人

    # 预计算后续人员的最大值之和、最小值之和（用于剪枝）
    suffix_max = sum(lst[0] for lst in num_lists[idx + 1:])   # 每个列表第一个是最大值
    suffix_min = sum(lst[-1] for lst in num_lists[idx + 1:])  # 每个列表最后一个是最小值

    for val in num_lists[idx]:
        remain = target - val

        # 上限剪枝：剩余目标 < 后续所有人选最小值之和 → 当前val太大，
        # 但因为列表从大到小，后面的val更小，remain更大，还有可能，所以不能break
        # 不对，remain = target - val，val从大到小，remain从小到大
        # 如果 remain < suffix_min → val太大，remain太小，后续凑不够 suffix_min → 跳过这个val，继续看更小的val
        if remain < suffix_min:
            continue

        # 下限剪枝：剩余目标 > 后续所有人选最大值之和 → 当前val太小
        # val从大到小，后面的val更小，remain更大，更不可能 → 直接break
        if remain > suffix_max:
            break

        current_combo.append(val)
        _dfs_amounts(num_lists, remain, idx + 1, current_combo, results, max_results)
        current_combo.pop()

        if len(results) >= max_results:
            return


def find_all_combinations(data: dict, N: int, enabled: list, initiators: list, max_results: int = MAX_SOLUTIONS):
    working = {k: v for k, v in data.items() if k in enabled} if enabled else dict(data)
    if not working:
        return [], []

    all_names = list(working.keys())
    init_names = [n for n in initiators if n in working] if initiators else all_names
    if not init_names:
        return [], []

    exact_solutions = []
    closest_solutions = []  # (diff, sol)

    for initiator in init_names:
        if len(exact_solutions) >= max_results:
            break
        if not working.get(initiator):
            continue

        others = [n for n in all_names if n != initiator and working.get(n)]

        for init_amt in working[initiator]:
            if len(exact_solutions) >= max_results:
                break

            if init_amt == N:
                exact_solutions.append({
                    'initiator': initiator,
                    'initiator_amount': init_amt,
                    'participants': [],
                    'total_people': 1,
                    'actual_sum': N,
                    'diff': 0,
                })
                continue

            diff = abs(init_amt - N)
            solo_sol = {
                'initiator': initiator,
                'initiator_amount': init_amt,
                'participants': [],
                'total_people': 1,
                'actual_sum': init_amt,
                'diff': diff,
            }
            closest_solutions.append((diff, solo_sol))

            if init_amt > N:
                continue

            remain = N - init_amt

            # 按人数从少到多枚举参与者组合
            for k in range(1, len(others) + 1):
                if len(exact_solutions) >= max_results:
                    break
                for combo_names in itertools.combinations(others, k):
                    if len(exact_solutions) >= max_results:
                        break

                    num_lists = [working[n] for n in combo_names]

                    # 快速剪枝：这组人的最大值之和 < remain → 不可能凑出
                    max_possible = sum(lst[0] for lst in num_lists)
                    if max_possible < remain:
                        continue
                    # 快速剪枝：这组人的最小值之和 > remain → 不可能凑出
                    min_possible = sum(lst[-1] for lst in num_lists)
                    if min_possible > remain:
                        continue

                    # DFS搜索，带剪枝
                    found_amounts = []
                    _dfs_amounts(num_lists, remain, 0, [], found_amounts, max_results - len(exact_solutions))

                    for amounts in found_amounts:
                        exact_solutions.append({
                            'initiator': initiator,
                            'initiator_amount': init_amt,
                            'participants': [
                                {'name': combo_names[i], 'amount': amounts[i]}
                                for i in range(k)
                            ],
                            'total_people': 1 + k,
                            'actual_sum': N,
                            'diff': 0,
                        })

                    # 同时记录最接近的（只取最接近的一个用于兜底）
                    if not found_amounts and k == 1:
                        for cn in combo_names:
                            for v in working[cn]:
                                actual = init_amt + v
                                d = abs(actual - N)
                                closest_solutions.append((d, {
                                    'initiator': initiator,
                                    'initiator_amount': init_amt,
                                    'participants': [{'name': cn, 'amount': v}],
                                    'total_people': 2,
                                    'actual_sum': actual,
                                    'diff': d,
                                }))

    exact_solutions.sort(key=lambda x: x['total_people'])
    exact_solutions = exact_solutions[:max_results]

    closest_solutions.sort(key=lambda x: (x[0], x[1]['total_people']))
    closest_results = []
    if closest_solutions:
        best_diff = closest_solutions[0][0]
        for diff, sol in closest_solutions:
            if diff == best_diff:
                closest_results.append(sol)
                if len(closest_results) >= max_results:
                    break
            else:
                break

    return exact_solutions, closest_results


def _dfs_exact_plans(working, all_names, init_names, N):
    """
    枚举所有能精确凑出 N 的方案，返回列表。
    利用排序做剪枝加速。
    """
    all_plans = []

    for initiator in init_names:
        if not working.get(initiator):
            continue
        others = [n for n in all_names if n != initiator and working.get(n)]

        for init_amt in working[initiator]:
            if init_amt > N:
                continue
            if init_amt == N:
                all_plans.append({
                    'initiator': initiator,
                    'initiator_amount': init_amt,
                    'participants': [],
                    'total_people': 1,
                    'actual_sum': N,
                    'diff': 0,
                    'people_set': frozenset({initiator}),
                })
                continue

            remain = N - init_amt

            for k in range(1, len(others) + 1):
                for combo_names in itertools.combinations(others, k):
                    num_lists = [working[n] for n in combo_names]

                    # 快速剪枝
                    max_possible = sum(lst[0] for lst in num_lists)
                    if max_possible < remain:
                        continue
                    min_possible = sum(lst[-1] for lst in num_lists)
                    if min_possible > remain:
                        continue

                    found_amounts = []
                    _dfs_amounts(num_lists, remain, 0, [], found_amounts, 500)

                    for amounts in found_amounts:
                        pset = frozenset({initiator} | set(combo_names))
                        all_plans.append({
                            'initiator': initiator,
                            'initiator_amount': init_amt,
                            'participants': [
                                {'name': combo_names[i], 'amount': amounts[i]}
                                for i in range(k)
                            ],
                            'total_people': 1 + k,
                            'actual_sum': N,
                            'diff': 0,
                            'people_set': pset,
                        })

    return all_plans


def solve_system_mode(data: dict, N: int, enabled: list, initiators: list):
    """
    系统解算模式：每个人最多发起一次、最多参与一次，
    在此约束下凑出尽量多的目标金额 N，返回一组最优解。
    """
    working = {k: v for k, v in data.items() if k in enabled} if enabled else dict(data)
    if not working:
        return []

    all_names = list(working.keys())
    init_names = [n for n in initiators if n in working] if initiators else all_names
    if not init_names:
        return []

    # 第一步：枚举所有精确方案
    all_plans = _dfs_exact_plans(working, all_names, init_names, N)

    if not all_plans:
        return []

    # 去重
    seen = set()
    unique_plans = []
    for p in all_plans:
        key = (p['initiator'], p['initiator_amount'],
               tuple(sorted((pp['name'], pp['amount']) for pp in p['participants'])))
        if key not in seen:
            seen.add(key)
            unique_plans.append(p)

    # 按人数少优先（占用资源少的方案优先尝试）
    unique_plans.sort(key=lambda x: x['total_people'])

    # 预处理：为每个方案建立冲突索引，加速回溯
    n_plans = len(unique_plans)
    # conflicts[i] = set of plan indices that conflict with plan i
    plan_people = [p['people_set'] for p in unique_plans]
    conflicts = [set() for _ in range(n_plans)]
    for i in range(n_plans):
        for j in range(i + 1, n_plans):
            if plan_people[i] & plan_people[j]:
                conflicts[i].add(j)
                conflicts[j].add(i)

    best_result = []
    total_people_count = len(all_names)

    def backtrack(idx, used_people, current_selection, skip_set):
        nonlocal best_result

        # 理论上限：当前已选 + 剩余中最多能选几个（乐观估计：每个方案只用1人）
        remaining_capacity = total_people_count - len(used_people)
        optimistic_remaining = min(n_plans - idx, remaining_capacity)
        if len(current_selection) + optimistic_remaining <= len(best_result):
            return

        if len(current_selection) > len(best_result):
            best_result = current_selection[:]

        for i in range(idx, n_plans):
            if i in skip_set:
                continue
            plan = unique_plans[i]
            if plan['people_set'] & used_people:
                continue

            new_skip = skip_set | conflicts[i]
            current_selection.append(plan)
            backtrack(i + 1, used_people | plan['people_set'], current_selection, new_skip)
            current_selection.pop()

    backtrack(0, frozenset(), [], set())

    result = []
    for plan in best_result:
        clean = {k: v for k, v in plan.items() if k != 'people_set'}
        result.append(clean)

    return result


@app.route('/')
def index():
    data = load_data_from_excel(EXCEL_FILE)
    people = []
    for name, nums in data.items():
        people.append({'name': name, 'numbers': nums})
    return render_template('index.html', people=people)


@app.route('/calculate', methods=['POST'])
def calculate():
    payload = request.get_json()
    targets = payload.get('targets', [])
    enabled = payload.get('enabled', [])
    initiators = payload.get('initiators', [])

    data = load_data_from_excel(EXCEL_FILE)

    all_results = {}
    for N in targets:
        try:
            N = int(N)
        except (ValueError, TypeError):
            continue
        exact, closest = find_all_combinations(data, N, enabled, initiators)
        all_results[N] = {
            'exact': exact,
            'closest': closest,
        }

    return jsonify(all_results)


@app.route('/system_solve', methods=['POST'])
def system_solve():
    payload = request.get_json()
    targets = payload.get('targets', [])
    enabled = payload.get('enabled', [])
    initiators = payload.get('initiators', [])

    data = load_data_from_excel(EXCEL_FILE)

    all_results = {}
    for N in targets:
        try:
            N = int(N)
        except (ValueError, TypeError):
            continue
        solutions = solve_system_mode(data, N, enabled, initiators)
        all_results[N] = solutions

    return jsonify(all_results)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
