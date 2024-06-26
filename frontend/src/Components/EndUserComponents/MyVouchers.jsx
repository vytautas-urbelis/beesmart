import MyVouchersOngoing from "./MyVouchersComponents/MyVouchersOngoing.jsx";
import MyVouchersClosed from "./MyVouchersComponents/MyVouchersClosed.jsx";
import { useEffect, useState } from "react";
import { getActiveUserVouchers } from "../../axios/axiosVouchers";
import { getUsedUserVouchers } from "../../axios/axiosVouchers.js";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faLock, faPersonRunning } from "@fortawesome/free-solid-svg-icons";

const MyVouchers = () => {
  const [currentVouchers, setCurrentVouchers] = useState("ongoing");
  const [loading, setLoading] = useState(true);
  const [activeVouchers, setActiveVouchers] = useState(null);
  const [usedVouchers, setUsedVouchers] = useState(null);

  useEffect(() => {
    setLoading(true);
    const getVouchers = async () => {
      try {
        const activeVouchers = await getActiveUserVouchers();
        const usedVouchers = await getUsedUserVouchers();
        setActiveVouchers(activeVouchers);
        console.log(activeVouchers);
        setUsedVouchers(usedVouchers);
      } finally {
        setTimeout(() => {
          setLoading(false);
        }, 950);
      }
    };
    getVouchers();
  }, []);

  const handleToggleVouchers = (e, cardsOption) => {
    e.preventDefault();
    cardsOption === "ongoing" ? setCurrentVouchers("ongoing") : setCurrentVouchers("closed");
  };

  return (
    <>
    <section className="py-10 bg-transparent md:bg-base-100/50">
    {/* <div className="lg:w-[80%] md:w-[90%] xs:w-[80%] mx-10 md:mx-auto "> */}
      <div className="lg:w-[88%] md:w-[80%] xs:w-[100%] mx-auto bg-tsansparent pt-6  ">
      <header className=" mx-auto flex flex-row  justify-center items-center">
        <span className="mt-8 ">
          <a
            href="#"
            className="`cursor-pointer flex flex-col items-center pl-15 hover:font-bold  mx-2 my-2 md:mx-10 lg:mx-8 lg:my-0 xl:mx-12 ${active ?
         'text-secondary' : ''}`"
            onClick={(e) => {
              handleToggleVouchers(e, "ongoing");
            }}
          >
            <FontAwesomeIcon icon={faPersonRunning} />
            Active
          </a>
        </span>
        <span className="mt-8">
          <a
            href="#"
            className="`cursor-pointer flex flex-col items-center pl-15 hover:font-bold  mx-2 my-2 md:mx-10 lg:mx-8 lg:my-0 xl:mx-12 ${active ?
         'text-secondary' : ''}`"
            onClick={(e) => {
              handleToggleVouchers(e, "closed");
            }}
          >
            <FontAwesomeIcon icon={faLock} />
            Used
          </a>
        </span>
      </header>
      {loading ? (
        <div className="flex justify-center pt-8 pb-20">
          <div className="rounded-md bg-zinc-50 flex flex-col text-primary-content breadcrumbs w-80 shadow-md">
            <div className="pt-64 pb-64">
              <span className="loading loading-ball loading-lg"></span>
            </div>
          </div>
        </div>
      ) : (
        <main>
          {currentVouchers === "ongoing" && <MyVouchersOngoing loadin={loading} activeVouchers={activeVouchers} />}

          {currentVouchers === "closed" && <MyVouchersClosed loading={loading} usedVouchers={usedVouchers} />}
        </main>
      )}
    </div>
    
    </section>
    </>
  );
};

export default MyVouchers;
